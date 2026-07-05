//+------------------------------------------------------------------+
//| V9_Sonde_M1.mq4                                                  |
//| PowerFlow V9 — Sonde M1 dediee, mode tick/velocite                |
//|                                                                  |
//| Contrairement a V9_Sonde_TF.mq4 (candle-close, timer), cette     |
//| sonde tourne a CHAQUE tick (OnTick, pas de timer) et calcule une |
//| vitesse instantanee par devise sur une fenetre glissante de      |
//| quelques secondes. Reconstruction propre : aucun code V8 repris. |
//|                                                                  |
//| Deploiement : 1 seule instance, sur un chart au timeframe M1.    |
//|                                                                  |
//| Couche cognitive : cette sonde ne fait QUE lire et transmettre.  |
//| Aucune logique de trading, aucun ordre, aucune decision.         |
//+------------------------------------------------------------------+
#property strict

#import "Ws2_32.dll"
int    socket(int af, int type, int protocol);
int    connect(int s, int& name[], int namelen);
int    send(int s, uchar& buf[], int len, int flags);
int    closesocket(int s);
int    WSAStartup(ushort wVersionRequested, int& lpWSAData[]);
int    WSACleanup();
#import

//--- Parametres indicateur -------------------------------------------------
input string IndName            = "SDI TCSWL 600+";
input string RefSymbol          = "";

//--- Parametres reseau ---------------------------------------------------
// Port TCP du serveur de capture Python (core/v9/capture_server.py).
// 31685 = port de reference V9 (V8 l'occupe en production) ; 31690 = port de
// test V9 le temps de ne pas interrompre V8. Voir docs/deployment/V9_DEPLOYMENT_GUIDE.md.
input int    ServerPort             = 31685;

//--- Parametres de capture ---------------------------------------------------
input int    VelocityWindowMs      = 5000;  // Fenetre glissante pour nb_ticks / vitesse (alignee STALE_GATE M1 = 5000ms)
input double MinForceDelta         = 0.05;  // Seuil de variation minimum (sur au moins une devise) pour renvoyer un tick
input bool   IncludeOHLC           = true;
input bool   IncludeSpread         = true;
input bool   IncludeBidAsk         = true;
input bool   EnableAntiDuplicate   = true;  // Anti-duplicate strict : couple au seuil MinForceDelta
input bool   DebugPrint            = false;
input bool   ReplayOnInit          = true;  // Rejoue l'historique M1 ferme au demarrage (bougies closes, pas des ticks)
input int    ReplayBars            = 600;

input int    BrokerUTCOffsetHours  = 3; // Voir V9_Sonde_README.md — a verifier a chaque changement DST broker

//--- Ordre reel des buffers SDI (voir V9_Sonde_TF.mq4 pour le detail) --------
input int    BufIdx_AUD = 0;
input int    BufIdx_GBP = 1;
input int    BufIdx_JPY = 2;
input int    BufIdx_USD = 3;
input int    BufIdx_CAD = 4;
input int    BufIdx_EUR = 5;
input int    BufIdx_CHF = 6;
input int    BufIdx_NZD = 7;

//--- Etat global --------------------------------------------------------------
string   g_symbol;
string   g_lastSig = "";
int      g_sequence = 0;

// Ring buffer de la fenetre glissante — 1 entree par tick retenu.
#define  RING_SIZE 500
int      g_ringHead  = 0;
int      g_ringCount = 0;
long     g_ringTimeMs[RING_SIZE];
double   g_ringUsd[RING_SIZE], g_ringGbp[RING_SIZE], g_ringEur[RING_SIZE], g_ringJpy[RING_SIZE];
double   g_ringCad[RING_SIZE], g_ringChf[RING_SIZE], g_ringAud[RING_SIZE], g_ringNzd[RING_SIZE];

//+------------------------------------------------------------------+
int OnInit() {
   int wsa[100];
   WSAStartup(0x0202, wsa);
   g_symbol = (RefSymbol == "") ? Symbol() : RefSymbol;
   SymbolSelect(g_symbol, true);

   if(Period() != PERIOD_M1 && DebugPrint)
      Print("[V9 Sonde M1] ATTENTION : chart courant n'est pas M1 (Period()=", Period(), ").");

   if(DebugPrint) Print("[V9 Sonde M1] Init | Symbol=", g_symbol, " Window=", VelocityWindowMs, "ms");

   if(ReplayOnInit) ReplayHistory();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { WSACleanup(); }

//+------------------------------------------------------------------+
//| CHAQUE TICK — pas de timer, mode reactif pur                      |
//+------------------------------------------------------------------+
void OnTick() {
   double usd,gbp,eur,jpy,cad,chf,aud,nzd;
   if(!ReadSDI(g_symbol, PERIOD_M1, 0, usd,gbp,eur,jpy,cad,chf,aud,nzd)) {
      if(DebugPrint) Print("[V9 Sonde M1] SDI non chargee ou invalide -> skip");
      return;
   }

   long nowMs = GetTickCount64Safe();
   PushSample(nowMs, usd,gbp,eur,jpy,cad,chf,aud,nzd);
   PurgeOldSamples(nowMs);

   double vUsd,vGbp,vEur,vJpy,vCad,vChf,vAud,vNzd;
   ComputeVelocity(nowMs, usd,gbp,eur,jpy,cad,chf,aud,nzd,
                   vUsd,vGbp,vEur,vJpy,vCad,vChf,vAud,vNzd);

   string sig = MakeSig(usd,gbp,eur,jpy,cad,chf,aud,nzd);
   if(EnableAntiDuplicate && IsBelowMinDelta(sig)) return;

   datetime barTime   = iTime(g_symbol, PERIOD_M1, 0);
   datetime closeTime = barTime + PeriodSeconds(PERIOD_M1);
   datetime srvTime   = TimeCurrent();

   double op,hi,lo,cl; long vol; int spr; double spPr,bid,ask,mid;
   ReadOHLC(g_symbol, PERIOD_M1, 0, op,hi,lo,cl,vol,spr,spPr,bid,ask,mid);

   g_sequence++;
   string snapId = MakeSnapshotId(g_symbol, srvTime, g_sequence);

   string json = MakeJSON(snapId, g_symbol,
                          barTime, closeTime, srvTime, srvTime,
                          0, false,
                          op,hi,lo,cl,vol,spr,spPr,bid,ask,mid,
                          usd,gbp,eur,jpy,cad,chf,aud,nzd,
                          vUsd,vGbp,vEur,vJpy,vCad,vChf,vAud,vNzd,
                          g_ringCount);

   if(SendToPython(json)) {
      Remember(sig);
      if(DebugPrint) Print("[V9 Sonde M1] Sent | ", g_symbol, " ticks_fenetre=", g_ringCount);
   } else {
      if(DebugPrint) Print("[V9 Sonde M1] Envoi TCP echoue");
   }
}

//+------------------------------------------------------------------+
//| REPLAY HISTORIQUE — bougies M1 FERMEES uniquement (shift >= 1)    |
//| Le replay ne simule pas des ticks : il envoie l'etat de cloture   |
//| de chaque bougie M1 passee, avec vitesse/nb_ticks a zero (donnee  |
//| tick non disponible en historique).                              |
//+------------------------------------------------------------------+
void ReplayHistory() {
   int bars = MathMax(1, ReplayBars);
   int sent = 0;
   Print("[V9 Sonde M1 REPLAY] Debut | ", g_symbol, " | bars=", bars);
   for(int sh = bars; sh >= 1; sh--) {
      if(!HasUsableBar(g_symbol, PERIOD_M1, sh)) continue;

      double usd,gbp,eur,jpy,cad,chf,aud,nzd;
      if(!ReadSDI(g_symbol, PERIOD_M1, sh, usd,gbp,eur,jpy,cad,chf,aud,nzd)) continue;

      datetime barTime   = iTime(g_symbol, PERIOD_M1, sh);
      datetime closeTime = barTime + PeriodSeconds(PERIOD_M1);
      datetime srvTime   = TimeCurrent();

      double op,hi,lo,cl; long vol; int spr; double spPr,bid,ask,mid;
      ReadOHLC(g_symbol, PERIOD_M1, sh, op,hi,lo,cl,vol,spr,spPr,bid,ask,mid);

      g_sequence++;
      string snapId = MakeSnapshotId(g_symbol, srvTime, g_sequence);
      string json = MakeJSON(snapId, g_symbol,
                             barTime, closeTime, srvTime, srvTime,
                             sh, true,
                             op,hi,lo,cl,vol,spr,spPr,bid,ask,mid,
                             usd,gbp,eur,jpy,cad,chf,aud,nzd,
                             0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,
                             0);
      if(SendToPython(json)) sent++;
      Sleep(5);
      if(sent % 100 == 0 && sent > 0) Print("[V9 Sonde M1 REPLAY] ...", sent, "/", bars);
   }
   Print("[V9 Sonde M1 REPLAY] Termine | ", sent, " shifts envoyes");
}

//+------------------------------------------------------------------+
//| FENETRE GLISSANTE — ring buffer                                   |
//+------------------------------------------------------------------+
void PushSample(long tMs, double usd,double gbp,double eur,double jpy,
                double cad,double chf,double aud,double nzd) {
   int idx;
   if(g_ringCount < RING_SIZE) {
      idx = (g_ringHead + g_ringCount) % RING_SIZE;
      g_ringCount++;
   } else {
      idx = g_ringHead;
      g_ringHead = (g_ringHead + 1) % RING_SIZE; // ecrase le plus ancien
   }
   g_ringTimeMs[idx] = tMs;
   g_ringUsd[idx]=usd; g_ringGbp[idx]=gbp; g_ringEur[idx]=eur; g_ringJpy[idx]=jpy;
   g_ringCad[idx]=cad; g_ringChf[idx]=chf; g_ringAud[idx]=aud; g_ringNzd[idx]=nzd;
}

void PurgeOldSamples(long nowMs) {
   while(g_ringCount > 1 && (nowMs - g_ringTimeMs[g_ringHead]) > VelocityWindowMs) {
      g_ringHead = (g_ringHead + 1) % RING_SIZE;
      g_ringCount--;
   }
}

void ComputeVelocity(long nowMs,
                     double usd,double gbp,double eur,double jpy,
                     double cad,double chf,double aud,double nzd,
                     double& vUsd,double& vGbp,double& vEur,double& vJpy,
                     double& vCad,double& vChf,double& vAud,double& vNzd) {
   double dtSec = (nowMs - g_ringTimeMs[g_ringHead]) / 1000.0;
   if(g_ringCount < 2 || dtSec <= 0.0) {
      vUsd=vGbp=vEur=vJpy=vCad=vChf=vAud=vNzd=0.0;
      return;
   }
   int h = g_ringHead;
   vUsd = (usd - g_ringUsd[h]) / dtSec;
   vGbp = (gbp - g_ringGbp[h]) / dtSec;
   vEur = (eur - g_ringEur[h]) / dtSec;
   vJpy = (jpy - g_ringJpy[h]) / dtSec;
   vCad = (cad - g_ringCad[h]) / dtSec;
   vChf = (chf - g_ringChf[h]) / dtSec;
   vAud = (aud - g_ringAud[h]) / dtSec;
   vNzd = (nzd - g_ringNzd[h]) / dtSec;
}

//+------------------------------------------------------------------+
//| LECTURE SDI — meme ordre verifie que V9_Sonde_TF.mq4               |
//+------------------------------------------------------------------+
bool ReadSDI(string sym, int tf, int shift,
             double& usd, double& gbp, double& eur, double& jpy,
             double& cad, double& chf, double& aud, double& nzd) {
   aud = iCustom(sym, tf, IndName, BufIdx_AUD, shift);
   gbp = iCustom(sym, tf, IndName, BufIdx_GBP, shift);
   jpy = iCustom(sym, tf, IndName, BufIdx_JPY, shift);
   usd = iCustom(sym, tf, IndName, BufIdx_USD, shift);
   cad = iCustom(sym, tf, IndName, BufIdx_CAD, shift);
   eur = iCustom(sym, tf, IndName, BufIdx_EUR, shift);
   chf = iCustom(sym, tf, IndName, BufIdx_CHF, shift);
   nzd = iCustom(sym, tf, IndName, BufIdx_NZD, shift);

   if(AllInvalid(usd,gbp,eur,jpy,cad,chf,aud,nzd)) return false;
   return true;
}

void ReadOHLC(string sym, int tf, int shift,
              double& op, double& hi, double& lo, double& cl,
              long& vol, int& spr, double& spPr,
              double& bid, double& ask, double& mid) {
   op  = IncludeOHLC ? iOpen(sym, tf, shift)  : 0.0;
   hi  = IncludeOHLC ? iHigh(sym, tf, shift)  : 0.0;
   lo  = IncludeOHLC ? iLow(sym, tf, shift)   : 0.0;
   cl  = IncludeOHLC ? iClose(sym, tf, shift) : 0.0;
   vol = iVolume(sym, tf, shift);
   spr  = IncludeSpread ? (int)MarketInfo(sym, MODE_SPREAD) : 0;
   spPr = spr * MarketInfo(sym, MODE_POINT);
   bid  = IncludeBidAsk ? MarketInfo(sym, MODE_BID) : 0.0;
   ask  = IncludeBidAsk ? MarketInfo(sym, MODE_ASK) : 0.0;
   mid  = (bid > 0 && ask > 0) ? (bid + ask) / 2.0 : 0.0;
}

//+------------------------------------------------------------------+
//| CONSTRUCTION JSON — aligne FORMAT_FORCES.md (bloc "m1")           |
//+------------------------------------------------------------------+
string MakeJSON(string snapId, string sym,
                datetime barT, datetime closeT, datetime srvT, datetime capT,
                int shift, bool isClosed,
                double op, double hi, double lo, double cl,
                long vol, int spr, double spPr,
                double bid, double ask, double mid,
                double usd, double gbp, double eur, double jpy,
                double cad, double chf, double aud, double nzd,
                double vUsd, double vGbp, double vEur, double vJpy,
                double vCad, double vChf, double vAud, double vNzd,
                int nbTicksFenetre) {
   return StringFormat(
      "{"
      "\"schema_version\":\"1.0\","
      "\"snapshot_id\":\"%s\","
      "\"timestamp\":\"%s\","
      "\"source\":\"MT4_SDI\","
      "\"symbol\":\"%s\","
      "\"timeframe\":\"M1\","
      "\"mode\":\"tick_velocity\","
      "\"bar_time\":%d,\"bar_close_time\":%d,"
      "\"server_time\":%d,\"capture_time\":%d,"
      "\"shift\":%d,\"is_closed_bar\":%s,"
      "\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,"
      "\"tick_volume\":%d,"
      "\"spread_points\":%d,\"spread_price\":%.5f,"
      "\"bid\":%.5f,\"ask\":%.5f,\"mid\":%.5f,"
      "\"force_usd\":%.4f,\"force_gbp\":%.4f,\"force_eur\":%.4f,\"force_jpy\":%.4f,"
      "\"force_cad\":%.4f,\"force_chf\":%.4f,\"force_aud\":%.4f,\"force_nzd\":%.4f,"
      "\"vitesse_tick_usd\":%.4f,\"vitesse_tick_gbp\":%.4f,\"vitesse_tick_eur\":%.4f,\"vitesse_tick_jpy\":%.4f,"
      "\"vitesse_tick_cad\":%.4f,\"vitesse_tick_chf\":%.4f,\"vitesse_tick_aud\":%.4f,\"vitesse_tick_nzd\":%.4f,"
      "\"nb_ticks_fenetre\":%d,\"fenetre_ms\":%d,"
      "\"dernier_tick_timestamp\":\"%s\","
      "\"bridge_version\":\"V9_SONDE_M1\""
      "}",
      snapId, ToISO8601UTC(capT),
      sym,
      (int)barT, (int)closeT,
      (int)srvT, (int)capT,
      shift, (isClosed ? "true" : "false"),
      op, hi, lo, cl, (int)vol,
      spr, spPr, bid, ask, mid,
      usd, gbp, eur, jpy, cad, chf, aud, nzd,
      vUsd, vGbp, vEur, vJpy, vCad, vChf, vAud, vNzd,
      nbTicksFenetre, VelocityWindowMs,
      ToISO8601UTC(capT));
}

//+------------------------------------------------------------------+
//| TCP — 127.0.0.1:ServerPort (port configurable, voir input)        |
//+------------------------------------------------------------------+
// Encode AF_INET (2) + port (network byte order) dans un seul int32, tel
// qu'attendu par la structure sockaddr_in packee pour l'appel Winsock
// connect(). Remplace l'ancienne constante figee qui codait en dur le
// port 31685 : desormais calcule depuis l'input ServerPort.
int MakeSockAddr0(int port) {
   int hi = (port >> 8) & 0xFF;
   int lo = port & 0xFF;
   return 2 + (hi << 16) + (lo << 24);
}

bool SendToPython(string message) {
   int sock = socket(2, 1, 6);
   if(sock == -1) { if(DebugPrint) Print("[V9 Sonde M1] socket() failed"); return false; }
   int addr[4];
   addr[0] = MakeSockAddr0(ServerPort);
   addr[1] = 0x0100007F; // 127.0.0.1 en network byte order
   addr[2] = 0; addr[3] = 0;
   if(connect(sock, addr, 16) != 0) {
      if(DebugPrint) Print("[V9 Sonde M1] connect() failed");
      closesocket(sock); return false;
   }
   uchar buf[];
   StringToCharArray(message, buf, 0, WHOLE_ARRAY, CP_UTF8);
   int bytes = send(sock, buf, ArraySize(buf)-1, 0);
   closesocket(sock);
   if(bytes <= 0) { if(DebugPrint) Print("[V9 Sonde M1] send failed"); return false; }
   return true;
}

//+------------------------------------------------------------------+
//| UTILITAIRES                                                       |
//+------------------------------------------------------------------+
bool HasUsableBar(string sym, int tf, int shift) {
   return (iTime(sym, tf, shift) > 0 && iClose(sym, tf, shift) > 0);
}

bool AllInvalid(double a,double b,double c,double d,
                double e,double f,double g,double h) {
   if(IsOK(a)||IsOK(b)||IsOK(c)||IsOK(d)||
      IsOK(e)||IsOK(f)||IsOK(g)||IsOK(h)) return false;
   return true;
}

bool IsOK(double v) {
   if(v == EMPTY_VALUE) return false;
   if(v != v) return false;
   if(MathAbs(v) > 1000000.0) return false;
   return true;
}

// Signature courte (2 decimales) utilisee pour detecter une variation
// significative — plus stricte que la sonde TF car basee sur un seuil,
// pas seulement l'egalite stricte.
string MakeSig(double a,double b,double c,double d,
              double e,double f,double gg,double h) {
   return StringFormat("%.2f|%.2f|%.2f|%.2f|%.2f|%.2f|%.2f|%.2f", a,b,c,d,e,f,gg,h);
}

// Anti-duplicate strict : refuse le tick si aucune des 8 forces n'a
// bouge de plus de MinForceDelta depuis le dernier envoi.
bool IsBelowMinDelta(string sig) {
   if(g_lastSig == "") return false; // premier tick : toujours envoyer
   double prev[8], cur[8];
   if(!ParseSig(g_lastSig, prev) || !ParseSig(sig, cur)) return false;
   for(int i = 0; i < 8; i++)
      if(MathAbs(cur[i] - prev[i]) >= MinForceDelta) return false;
   return true;
}

bool ParseSig(string sig, double& out[]) {
   string parts[];
   int n = StringSplit(sig, '|', parts);
   if(n != 8) return false;
   for(int i = 0; i < 8; i++) out[i] = StringToDouble(parts[i]);
   return true;
}

void Remember(string sig) { g_lastSig = sig; }

string MakeSnapshotId(string sym, datetime t, int seq) {
   return StringFormat("v9-%s-M1-%d-%06d", sym, (int)t, seq);
}

string ToISO8601UTC(datetime t) {
   datetime u = t - BrokerUTCOffsetHours * 3600;
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02d.000Z",
                       TimeYear(u), TimeMonth(u), TimeDay(u),
                       TimeHour(u), TimeMinute(u), TimeSeconds(u));
}

// GetTickCount() peut deborder (32 bits, ~49.7 jours). Pour une fenetre de
// quelques secondes seulement, ce debordement n'a pas d'impact pratique :
// au pire un calcul de vitesse ignore sur un seul tick apres reboot long.
long GetTickCount64Safe() {
   return (long)GetTickCount();
}
//+------------------------------------------------------------------+
