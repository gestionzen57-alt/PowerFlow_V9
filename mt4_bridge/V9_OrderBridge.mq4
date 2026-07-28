//+------------------------------------------------------------------+
//|                                              V9_OrderBridge.mq4  |
//|                                       PowerFlow V9 Order Bridge  |
//|                            Phase 12 degel motion CEO 2026-07-28  |
//+------------------------------------------------------------------+
//| Description : EA MT4 qui poll le dossier data/order_queue/*.json |
//| du systeme V9 et execute les ordres envoyes.                    |
//|                                                                    |
//| Convention V9 : chaque fichier JSON contient un OrderRequest :    |
//|   {                                                                 |
//|     "command_id": "uuid",                                           |
//|     "decision_id": "trade_id",                                     |
//|     "symbol": "GBPUSD",                                             |
//|     "direction": "haussiere" | "baissiere",                       |
//|     "lot": 0.01,                                                    |
//|     "sl_pips": 10.0,                                                |
//|     "tp_pips": 20.0,                                                |
//|     "magic": 90900001,                                              |
//|     "timestamp": "2026-07-28T..."                                   |
//|   }                                                                 |
//|                                                                    |
//| Apres execution reussie, le fichier est deplace vers              |
//| data/order_queue/processed/ pour eviter le double-traitement.      |
//| En cas d'echec : deplace vers data/order_queue/failed/ avec       |
//| suffixe _ERROR_<raison>.                                           |
//+------------------------------------------------------------------+
#property copyright "PowerFlow V9"
#property link      ""
#property version   "1.00"
#property strict

#include <Files\FileTxt.mqh>

// --- Configuration (modifiable dans les inputs MT4) ---
extern string  OrderQueuePath = "C:\\projet\\V9\\data\\order_queue";
extern string  ProcessedPath  = "C:\\projet\\V9\\data\\order_queue\\processed";
extern string  FailedPath     = "C:\\projet\\V9\\data\\order_queue\\failed";
extern int     PollSeconds    = 5;        // Intervalle de polling
extern int     Slippage       = 3;        // Slippage max en pips
extern int     MagicNumber    = 90900001; // Magic number V9
extern bool    DryRun         = true;    // MODE SAFE par defaut

// --- Variables globales ---
datetime lastPoll = 0;
int      totalProcessed = 0;
int      totalFailed = 0;

//+------------------------------------------------------------------+
//| Expert initialization                                              |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("[V9_OrderBridge] Demarrage EA V9_OrderBridge v1.00");
   Print("[V9_OrderBridge] OrderQueuePath = ", OrderQueuePath);
   Print("[V9_OrderBridge] DryRun = ", DryRun);
   Print("[V9_OrderBridge] PollSeconds = ", PollSeconds);
   
   // Creer les sous-dossiers si manquants
   if(!FolderCreate(ProcessedPath)) Print("[V9_OrderBridge] WARN: ", ProcessedPath, " existe deja ou erreur");
   if(!FolderCreate(FailedPath))    Print("[V9_OrderBridge] WARN: ", FailedPath, " existe deja ou erreur");
   
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                             |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("[V9_OrderBridge] Arret EA. Processed=", totalProcessed, " Failed=", totalFailed);
}

//+------------------------------------------------------------------+
//| Expert tick function                                               |
//+------------------------------------------------------------------+
void OnTick()
{
   if(TimeCurrent() - lastPoll < PollSeconds) return;
   lastPoll = TimeCurrent();
   
   PollOrderQueue();
}

//+------------------------------------------------------------------+
//| Poll le dossier order_queue et execute les ordres                  |
//+------------------------------------------------------------------+
void PollOrderQueue()
{
   // Trouver tous les fichiers .json dans OrderQueuePath
   string fileName;
   long   searchHandle = FileFindFirst(OrderQueuePath + "\\*.json", fileName);
   
   if(searchHandle == INVALID_HANDLE)
   {
      // Aucun ordre a traiter
      return;
   }
   
   // Iterer sur tous les fichiers
   do
   {
      string fullPath = OrderQueuePath + "\\" + fileName;
      ProcessOrderFile(fullPath, fileName);
   }
   while(FileFindNext(searchHandle, fileName));
   
   FileFindClose(searchHandle);
}

//+------------------------------------------------------------------+
//| Traiter un fichier d'ordre JSON                                    |
//+------------------------------------------------------------------+
void ProcessOrderFile(string fullPath, string fileName)
{
   Print("[V9_OrderBridge] Lecture fichier : ", fileName);
   
   // Lire le contenu JSON
   int fileHandle = FileOpen(fileName, FILE_READ|FILE_TXT|FILE_ANSI|FILE_SHARE_READ, '\n');
   if(fileHandle == INVALID_HANDLE)
   {
      Print("[V9_OrderBridge] ERREUR ouverture fichier : ", GetLastError());
      return;
   }
   
   string jsonContent = "";
   while(!FileIsEnding(fileHandle))
   {
      jsonContent += FileReadString(fileHandle) + "\n";
   }
   FileClose(fileHandle);
   
   // Parser JSON minimal (sans JSON library MT4 native)
   // Convention V9 : clefs fixes
   string symbol     = ExtractJsonValue(jsonContent, "symbol");
   string direction  = ExtractJsonValue(jsonContent, "direction");
   string lotStr     = ExtractJsonValue(jsonContent, "lot");
   string slStr      = ExtractJsonValue(jsonContent, "sl_pips");
   string tpStr      = ExtractJsonValue(jsonContent, "tp_pips");
   string decisionId = ExtractJsonValue(jsonContent, "decision_id");
   
   if(symbol == "" || direction == "" || lotStr == "")
   {
      MoveToFailed(fullPath, fileName, "JSON parsing incomplete");
      totalFailed++;
      return;
   }
   
   double lot    = StringToDouble(lotStr);
   double slPips = StringToDouble(slStr);
   double tpPips = StringToDouble(tpStr);
   
   // Conversion direction
   int cmd = (direction == "haussiere") ? OP_BUY : OP_SELL;
   
   // Calcul SL/TP en prix (depend du digits du symbole)
   int digits = (int)MarketInfo(symbol, MODE_DIGITS);
   double point = MarketInfo(symbol, MODE_POINT);
   double ask = MarketInfo(symbol, MODE_ASK);
   double bid = MarketInfo(symbol, MODE_BID);
   double entryPrice = (cmd == OP_BUY) ? ask : bid;
   
   double slPrice = 0, tpPrice = 0;
   if(slPips > 0) slPrice = (cmd == OP_BUY) ? entryPrice - slPips * point * 10 : entryPrice + slPips * point * 10;
   if(tpPips > 0) tpPrice = (cmd == OP_BUY) ? entryPrice + tpPips * point * 10 : entryPrice - tpPips * point * 10;
   
   // Mode DRY-RUN : ne pas envoyer l'ordre reel, juste logger
   if(DryRun)
   {
      Print("[V9_OrderBridge] DRY-RUN : ordre simule pour ", symbol,
            " dir=", direction, " lot=", lot, " sl=", slPips, " tp=", tpPips);
      // En DRY-RUN, on deplace quand meme vers processed/ pour eviter retry
      MoveToProcessed(fullPath, fileName);
      totalProcessed++;
      return;
   }
   
   // Mode LIVE : envoyer l'ordre reel
   int ticket = OrderSend(symbol, cmd, lot, entryPrice, Slippage, slPrice, tpPrice,
                          "V9_" + decisionId, MagicNumber, 0, CLR_NONE);
   
   if(ticket > 0)
   {
      Print("[V9_OrderBridge] ORDRE ENVOYE : ticket=", ticket,
            " symbol=", symbol, " lot=", lot, " sl=", slPrice, " tp=", tpPrice);
      MoveToProcessed(fullPath, fileName);
      totalProcessed++;
   }
   else
   {
      int err = GetLastError();
      Print("[V9_OrderBridge] ERREUR OrderSend : ", err, " ", ErrorDescription(err));
      MoveToFailed(fullPath, fileName, "OrderSend err=" + IntegerToString(err));
      totalFailed++;
   }
}

//+------------------------------------------------------------------+
//| Extraire une valeur string depuis JSON (parser minimal)            |
//+------------------------------------------------------------------+
string ExtractJsonValue(string json, string key)
{
   string pattern = "\"" + key + "\":";
   int pos = StringFind(json, pattern);
   if(pos < 0) return "";
   
   pos += StringLen(pattern);
   while(pos < StringLen(json) && (StringGetCharacter(json, pos) == ' ' || StringGetCharacter(json, pos) == '\t'))
      pos++;
   
   if(pos >= StringLen(json)) return "";
   
   char c = (char)StringGetCharacter(json, pos);
   if(c == '"') // String value
   {
      pos++;
      int end = StringFind(json, "\"", pos);
      if(end < 0) return "";
      return StringSubstr(json, pos, end - pos);
   }
   else // Numeric value
   {
      int end = pos;
      while(end < StringLen(json))
      {
         char cc = (char)StringGetCharacter(json, end);
         if(cc == ',' || cc == '}' || cc == '\n' || cc == ' ' || cc == '\r') break;
         end++;
      }
      return StringSubstr(json, pos, end - pos);
   }
}

//+------------------------------------------------------------------+
//| Deplacer un fichier vers processed/                                |
//+------------------------------------------------------------------+
void MoveToProcessed(string fullPath, string fileName)
{
   string dest = ProcessedPath + "\\" + fileName;
   if(!FileMove(fullPath, 0, dest, 0)) // FILE_REWRITE=0, FILE_COMMON=0
   {
      // Fallback : copier + supprimer
      Print("[V9_OrderBridge] WARN MoveToProcessed echoue pour ", fileName);
   }
}

//+------------------------------------------------------------------+
//| Deplacer un fichier vers failed/ avec suffixe erreur              |
//+------------------------------------------------------------------+
void MoveToFailed(string fullPath, string fileName, string reason)
{
   string ts = TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS);
   ts = StringReplace(ts, CharToString(':'), CharToString('-'));
   ts = StringReplace(ts, CharToString(' '), CharToString('_'));
   string suffix = "_ERROR_" + ts;
   string baseName = fileName;
   int dotPos = StringFind(baseName, ".json");
   if(dotPos > 0) baseName = StringSubstr(baseName, 0, dotPos);
   string dest = FailedPath + "\\" + baseName + suffix + ".json";
   if(!FileMove(fullPath, 0, dest, 0))
   {
      Print("[V9_OrderBridge] WARN MoveToFailed echoue pour ", fileName);
   }
}

//+------------------------------------------------------------------+
//| Description d'erreur MT4                                           |
//+------------------------------------------------------------------+
string ErrorDescription(int err)
{
   switch(err)
   {
      case 0:   return "No error";
      case 1:   return "No error but result unknown";
      case 2:   return "Common error";
      case 3:   return "Invalid parameter";
      case 4:   return "Server busy";
      case 5:   return "Old version of terminal";
      case 6:   return "No connection";
      case 7:   return "Insufficient rights";
      case 8:   return "Too frequent requests";
      case 64:  return "Account blocked";
      case 65:  return "Invalid account";
      case 128: return "Timeout";
      case 129: return "Invalid price";
      case 130: return "Invalid stops";
      case 131: return "Invalid trade volume";
      case 132: return "Market closed";
      case 133: return "Trade disallowed";
      case 134: return "Insufficient money";
      case 135: return "Price changed";
      case 136: return "No prices";
      case 137: return "Broker busy";
      case 138: return "Requote";
      case 139: return "Order locked";
      case 140: return "Long positions only allowed";
      case 141: return "Too many requests";
      default:  return "Unknown error " + IntegerToString(err);
   }
}
//+------------------------------------------------------------------+
