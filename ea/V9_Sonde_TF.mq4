//+------------------------------------------------------------------+
//| V9_Sonde_TF.mq4                                                  |
//| PowerFlow V9 — Sonde multi-timeframe (1 instance par TF)         |
//|                                                                  |
//| Reconstruction propre de la sonde forces. Ne reprend aucun code  |
//| V8 tel quel : structure reecrite, bugs connus corriges,          |
//| format JSON aligne sur docs/architecture/formats/FORMAT_FORCES.md|
//|                                                                  |
//| Deploiement : 1 instance par timeframe sur le meme symbole.      |
//|   Chart GBPUSD M5  -> une instance avec Period()=M5              |
//|   Chart GBPUSD M15 -> une instance avec Period()=M15             |
//|   ... etc pour M30, H1, H4, D1                                  |
//|   Pour M1, preferer l'EA dedie V9_Sonde_M1.mq4 (mode tick).      |
//|   Cette EA reste capable de tourner sur M1 en secours, mais      |
//|   n'implemente pas la capture vitesse/nb_ticks de V9_Sonde_M1.   |
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
input string IndName            = "SDI TCSWL 600+";  // Nom exact de l'indicateur SDI charge sur le chart
input string RefSymbol          = "";                 // Vide = symbole du chart courant

//--- Parametres de capture ---------------------------------------------------
input int    RefreshSeconds     = 1;     // Frequence du timer (secondes)
input int    ShiftIndex         = 1;     // 1 = bougie fermee (recommande M5..D1) | 0 = bougie en cours (M1 uniquement)
input bool   IncludeOHLC        = true;
input bool   IncludeSpread      = true;
input bool   IncludeBidAsk      = true;
input bool   IncludeTickVolume  = true;
input bool   EnableAntiDuplicate= true;
input bool   DebugPrint         = false;
input bool   ReplayOnInit       = true;   // Rejoue l'historique au demarrage pour combler les trous
input int    ReplayBars         = 600;    // Nombre de bougies fermees a rejouer

//--- Fuseau horaire broker ----------------------------------------------------
// FORMAT_FORCES.md exige un timestamp ISO8601 UTC. MT4 ne connait que l'heure
// serveur (broker) via TimeCurrent(). Il faut donc indiquer ici le decalage
// broker -> UTC courant (change avec l'heure ete/hiver du broker).
// Bug V8 connu : ce decalage n'etait jamais applique, toutes les heures
// stockees etaient en heure broker deguisee en UTC. Voir V9_Sonde_README.md.
input int    BrokerUTCOffsetHours = 3;   // Ex : broker Tickmill ete = UTC+3. A VERIFIER a chaque changement DST.

//--- Ordre reel des buffers de l'indicateur SDI -------------------------------
// IMPORTANT : cet ordre est une propriete de l'indicateur "SDI TCSWL 600+"
// lui-meme (verifie via SDI_Diagnostic, voir V9_Sonde_README.md), PAS un choix
// arbitraire de cette sonde. NE PAS modifier sans avoir re-verifie sur un
// chart avec l'outil de diagnostic decrit dans le README.
// Si un jour l'indicateur change d'ordre de buffers (nouvelle version DLL),
// remapper UNIQUEMENT ces 8 inputs, sans toucher au reste du code.
input int    BufIdx_AUD = 0;
input int    BufIdx_GBP = 1;
input int    BufIdx_JPY = 2;
input int    BufIdx_USD = 3;
input int    BufIdx_CAD = 4;
input int    BufIdx_EUR = 5;
input int    BufIdx_CHF = 6;
input int    BufIdx_NZD = 7;

//--- Etat global de l'instance -------------------------------------------------
int      g_wsaData[100];
string   g_symbol;
int      g_tf;
string   g_tfName;
string   g_lastKey = "";
string   g_lastSig = "";
int      g_sequence = 0;

//+------------------------------------------------------------------+
int OnInit() {
   WSAStartup(0x0202, g_wsaData);
   g_symbol = (RefSymbol == "") ? Symbol() : RefSymbol;
   SymbolSelect(g_symbol, true);
   g_tf     = Period();
   g_tfName = TFName(g_tf);

   if(g_tf == PERIOD_M1 && DebugPrint)
      Print("[V9 Sonde TF] ATTENTION : instance M1 detectee. Pour la production, ",
            "preferer V9_Sonde_M1.mq4 (mode tick/velocite dedie).");

   EventSetTimer(MathMax(1, RefreshSeconds));
   if(DebugPrint)
      Print("[V9 Sonde TF] Init | Symbol=", g_symbol, " TF=", g_tfName,
            " Refresh=", RefreshSeconds, "s Shift=", ShiftIndex);

   if(ReplayOnInit) ReplayHistory();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { EventKillTimer(); WSACleanup(); }
void OnTimer() { RunShift(ShiftIndex); }

//+------------------------------------------------------------------+
//| REPLAY HISTORIQUE — combler les trous au demarrage                |
//+------------------------------------------------------------------+
void ReplayHistory() {
   int bars = MathMax(1, ReplayBars);
   int sent = 0;
   Print("[V9 Sonde TF REPLAY] Debut | ", g_symbol, " ", g_tfName, " | bars=", bars);
   for(int sh = bars; sh >= 1; sh--) {
      RunShift(sh);
      sent++;
      Sleep(10);
      if(sent % 100 == 0) Print("[V9 Sonde TF REPLAY] ...", sent, "/", bars);
   }
   Print("[V9 Sonde TF REPLAY] Termine | ", sent, " shifts envoyes");
}

//+------------------------------------------------------------------+
//| CAPTURE D'UN SHIFT DONNE                                          |
//+------------------------------------------------------------------+
void RunShift(int sh) {
   if(!HasUsableBar(g_symbol, g_tf, sh)) return;

   double usd,gbp,eur,jpy,cad,chf,aud,nzd;
   if(!ReadSDI(g_symbol, g_tf, sh, usd,gbp,eur,jpy,cad,chf,aud,nzd)) {
      if(DebugPrint) Print("[V9 Sonde TF] SDI non chargee ou invalide sur ", g_symbol, " ", g_tfName, " shift=", sh, " -> skip");
      return;
   }

   datetime barTime   = iTime(g_symbol, g_tf, sh);
   datetime closeTime = barTime + PeriodSeconds(g_tf);
   datetime srvTime   = TimeCurrent();
   datetime capTime   = srvTime;

   double op,hi,lo,cl; long vol; int spr; double spPr,bid,ask,mid;
   ReadOHLC(g_symbol, g_tf, sh, op,hi,lo,cl,vol,spr,spPr,bid,ask,mid);

   string key = g_symbol + "_" + g_tfName;
   string sig = MakeSig(g_tf, barTime, usd,gbp,eur,jpy,cad,chf,aud,nzd, op,hi,lo,cl,vol);
   bool isClosed = (sh >= 1);

   if(EnableAntiDuplicate && sh == ShiftIndex && IsDuplicate(key, sig)) return;

   g_sequence++;
   string snapId = MakeSnapshotId(g_symbol, g_tfName, srvTime, g_sequence);

   string json = MakeJSON(snapId, g_symbol, g_tfName,
                          barTime, closeTime, srvTime, capTime,
                          sh, isClosed,
                          op,hi,lo,cl,vol,spr,spPr,bid,ask,mid,
                          usd,gbp,eur,jpy,cad,chf,aud,nzd);

   if(SendToPython(json)) {
      if(sh == ShiftIndex) Remember(key, sig);
      if(DebugPrint) Print("[V9 Sonde TF] Sent | ", g_symbol, " ", g_tfName, " bar=", TimeToString(barTime, TIME_MINUTES));
   } else {
      if(DebugPrint) Print("[V9 Sonde TF] Envoi TCP echoue | ", g_symbol, " ", g_tfName);
   }
}

//+------------------------------------------------------------------+
//| LECTURE SDI — ordre de buffers verifie, sortie en ordre canonique |
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
   vol = IncludeTickVolume ? iVolume(sym, tf, shift) : 0;
   spr  = IncludeSpread ? (int)MarketInfo(sym, MODE_SPREAD) : 0;
   spPr = spr * MarketInfo(sym, MODE_POINT);
   bid  = IncludeBidAsk ? MarketInfo(sym, MODE_BID) : 0.0;
   ask  = IncludeBidAsk ? MarketInfo(sym, MODE_ASK) : 0.0;
   mid  = (bid > 0 && ask > 0) ? (bid + ask) / 2.0 : 0.0;
}

//+------------------------------------------------------------------+
//| CONSTRUCTION JSON — aligne FORMAT_FORCES.md                       |
//+------------------------------------------------------------------+
string MakeJSON(string snapId, string sym, string tfName,
                datetime barT, datetime closeT, datetime srvT, datetime capT,
                int shift, bool isClosed,
                double op, double hi, double lo, double cl,
                long vol, int spr, double spPr,
                double bid, double ask, double mid,
                double usd, double gbp, double eur, double jpy,
                double cad, double chf, double aud, double nzd) {
   return StringFormat(
      "{"
      "\"schema_version\":\"1.0\","
      "\"snapshot_id\":\"%s\","
      "\"timestamp\":\"%s\","
      "\"source\":\"MT4_SDI\","
      "\"symbol\":\"%s\","
      "\"timeframe\":\"%s\","
      "\"bar_time\":%d,\"bar_close_time\":%d,"
      "\"server_time\":%d,\"capture_time\":%d,"
      "\"shift\":%d,\"is_closed_bar\":%s,"
      "\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,"
      "\"tick_volume\":%d,"
      "\"spread_points\":%d,\"spread_price\":%.5f,"
      "\"bid\":%.5f,\"ask\":%.5f,\"mid\":%.5f,"
      "\"force_usd\":%.4f,\"force_gbp\":%.4f,\"force_eur\":%.4f,\"force_jpy\":%.4f,"
      "\"force_cad\":%.4f,\"force_chf\":%.4f,\"force_aud\":%.4f,\"force_nzd\":%.4f,"
      "\"bridge_version\":\"V9_SONDE_TF\""
      "}",
      snapId, ToISO8601UTC(capT),
      sym, tfName,
      (int)barT, (int)closeT,
      (int)srvT, (int)capT,
      shift, (isClosed ? "true" : "false"),
      op, hi, lo, cl, (int)vol,
      spr, spPr, bid, ask, mid,
      usd, gbp, eur, jpy, cad, chf, aud, nzd);
}

//+------------------------------------------------------------------+
//| TCP — memes constantes Winsock que la sonde V8 (127.0.0.1:31685)  |
//+------------------------------------------------------------------+
bool SendToPython(string message) {
   int sock = socket(2, 1, 6); // AF_INET, SOCK_STREAM, IPPROTO_TCP
   if(sock == -1) { if(DebugPrint) Print("[V9 Sonde TF] socket() failed"); return false; }
   int addr[4];
   addr[0] = -981794814; // AF_INET (2) + port 31685 en network byte order, packes en int32
   addr[1] = 0x0100007F; // 127.0.0.1 en network byte order
   addr[2] = 0; addr[3] = 0;
   if(connect(sock, addr, 16) != 0) {
      if(DebugPrint) Print("[V9 Sonde TF] connect() failed");
      closesocket(sock); return false;
   }
   uchar buf[];
   StringToCharArray(message, buf, 0, WHOLE_ARRAY, CP_UTF8);
   int bytes = send(sock, buf, ArraySize(buf)-1, 0);
   closesocket(sock);
   if(bytes <= 0) { if(DebugPrint) Print("[V9 Sonde TF] send failed"); return false; }
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
   if(v != v) return false; // NaN
   if(MathAbs(v) > 1000000.0) return false;
   return true;
}

string MakeSig(int tf, datetime bt,
               double a,double b,double c,double d,
               double e,double f,double gg,double h,
               double op,double hi,double lo,double cl,long vol) {
   return StringFormat("%d|%d|%.2f|%.2f|%.2f|%.2f|%.2f|%.2f|%.2f|%.2f|%.5f|%.5f|%.5f|%.5f|%d",
                       tf,(int)bt,a,b,c,d,e,f,gg,h,op,hi,lo,cl,(int)vol);
}

bool IsDuplicate(string key, string sig) {
   return (g_lastKey == key && g_lastSig == sig);
}

void Remember(string key, string sig) {
   g_lastKey = key;
   g_lastSig = sig;
}

string MakeSnapshotId(string sym, string tfName, datetime t, int seq) {
   return StringFormat("v9-%s-%s-%d-%06d", sym, tfName, (int)t, seq);
}

// Convertit un datetime serveur (broker) en chaine ISO8601 UTC.
// Hypothese : t est exprime en heure broker ; on soustrait BrokerUTCOffsetHours
// pour obtenir l'heure UTC reelle. Voir V9_Sonde_README.md pour la procedure
// de verification de ce decalage.
string ToISO8601UTC(datetime t) {
   datetime u = t - BrokerUTCOffsetHours * 3600;
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02d.000Z",
                       TimeYear(u), TimeMonth(u), TimeDay(u),
                       TimeHour(u), TimeMinute(u), TimeSeconds(u));
}

string TFName(int tf) {
   switch(tf) {
      case PERIOD_M1:  return "M1";
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D1";
      case PERIOD_W1:  return "W1";
   }
   return IntegerToString(tf);
}
//+------------------------------------------------------------------+
