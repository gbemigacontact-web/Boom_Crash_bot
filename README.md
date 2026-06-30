# 🤖 Boom & Crash Bot — MANUS ELITE INTELLIGENCE

Bot de signaux de trading pour les indices synthétiques Boom & Crash de Deriv.
Analyse multi-timeframe (H4, H1, M30, M15, M5) avec notifications Telegram.

## Instruments couverts
- Boom 500 / Boom 900 / Boom 1000
- Crash 500 / Crash 900 / Crash 1000

## Stratégie implémentée

### Biais structurel
- **Boom** = tendance baissière de fond → signaux SELL prioritaires
- **Crash** = tendance haussière de fond → signaux BUY prioritaires

### 4 scénarios détectés
1. **Continuation de tendance** — Pullback sur OB/FVG + rejet dans la direction principale
2. **Post-spike recovery** — FVG créé par un spike, comblé avant reprise
3. **CHoCH & BOS** — Retournement structurel confirmé (utilisé avec parcimonie)
4. **Liquidity Sweep** — Chasse EQH/EQL puis retournement

### 5 confirmations obligatoires (4/5 minimum pour valider un signal)
1. Alignement de tendance H4 + H1 (EMA 20/50)
2. Prix dans une zone valide (Order Block ou Fair Value Gap)
3. Bougie de confirmation M5 (corps > 50%)
4. Momentum cohérent sur les 5 dernières bougies M5
5. SL structurel logique disponible

### Filtres de protection
- Spike détecté sur les 5 dernières bougies M5 → pas d'entrée
- Ratio R:R minimum 1:2.5

## Architecture

```
boom-crash-bot/
├── src/
│   ├── main.py              # Orchestrateur principal
│   ├── deriv_client.py      # Client WebSocket API Deriv
│   ├── analysis_engine.py   # Moteur d'analyse technique
│   └── telegram_notifier.py # Notifications Telegram
├── .github/
│   └── workflows/
│       └── boom_crash_bot.yml  # GitHub Actions (6 runs/jour)
├── requirements.txt
└── README.md
```

## Installation & Configuration

### 1. Fork / clone du dépôt sur GitHub

### 2. Créer les secrets GitHub
Dans ton dépôt → Settings → Secrets and variables → Actions → New repository secret :

| Secret | Description |
|--------|-------------|
| `DERIV_API_TOKEN` | Token API Deriv (lecture seule, créé sur app.deriv.com) |
| `DERIV_APP_ID` | App ID Deriv (utiliser `1089` pour les tests, créer le sien pour la prod) |
| `TELEGRAM_BOT_TOKEN` | Token du bot Telegram (depuis @BotFather) |
| `TELEGRAM_CHAT_ID` | ID de la conversation/canal où envoyer les signaux |

### 3. Créer ton token API Deriv
1. Connecte-toi sur **app.deriv.com**
2. Profil → Paramètres → API Token
3. Nom : `boom-crash-bot`, Permission : **Read**
4. Copier le token et l'ajouter comme secret `DERIV_API_TOKEN`

### 4. Récupérer ton TELEGRAM_CHAT_ID
Envoie un message à ton bot puis ouvre dans le navigateur :
```
https://api.telegram.org/bot<TON_TOKEN>/getUpdates
```
Le `chat_id` apparaît dans le JSON retourné.

### 5. Activer GitHub Actions
Les runs démarreront automatiquement selon le cron configuré.
Pour tester immédiatement : Actions → Boom & Crash Bot → Run workflow.

## Horaires des scans (UTC)
00:05 — 04:05 — 08:05 — 12:05 — 16:05 — 20:05

*(+1h en heure de l'Afrique de l'Ouest = 01:05 / 05:05 / 09:05 / 13:05 / 17:05 / 21:05)*

## Format d'un signal Telegram
```
🔴 SIGNAL VENTE (SELL)
Instrument : Boom 1000
Scénario : Liquidity sweep
Confiance : 5/6 confirmations

Entrée : 12345.6700
Stop Loss : 12378.4500
Take Profit : 12263.0450
Ratio R:R : 1:2.5

Confirmations validées :
  • Tendance alignée H4/H1: bearish
  • Sweep de liquidité EQH détecté (M15)
  • Prix dans un Order Block non mitigé
  • Bougie de confirmation M5 (corps 68%)
  • SL structurel placé (RR 1:2.5)

Biais structurel Boom: bearish

⚠️ Signal automatique — vérifier avant d'exécuter.
```

## ⚠️ Avertissement
Ce bot génère des signaux d'analyse technique. Il ne garantit aucun résultat.
Toujours vérifier manuellement les signaux avant toute exécution.
Le trading de produits synthétiques comporte des risques significatifs.
