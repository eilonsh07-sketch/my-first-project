# OptionDesk — 13 Agents

## Layer 0 — Infrastructure (תמיד ראשון)
| Agent | קובץ | Contract | תפקיד |
|-------|------|----------|-------|
| **ATLAS** ⭐ | `engine/atlas.py` NEW | `AnalysisPackage` | CEO Orchestrator — מנצח, לא מבצע |
| **VERIFY** | `engine/verify.py` NEW | `DataQualityReport` | שומר סף — בודק נתונים לפני כל backtest |

## Layer 1 — Data & Macro (אחרי VERIFY, במקביל)
| Agent | קובץ | Contract | תפקיד |
|-------|------|----------|-------|
| **KEYNES** | `engine/economist.py` ENHANCE | `MacroRegime` | Macro regime + VRP + חיבור לscoring.py |
| **MIKI** | `engine/research.py` NEW | `ResearchFindings` | ספרות אקדמית + הצעות פרמטרים |
| **RADAR** | `engine/radar.py` NEW | `EventCalendar` | earnings / ex-div / FOMC calendar |

## Layer 2 — Quantitative Core
| Agent | קובץ | Contract | תפקיד |
|-------|------|----------|-------|
| **MAX** ⭐ | `engine/backtest.py` ENHANCE | `BacktestResult` | Backtest + ALPHA/BETA dual validators |
| **SIGMA** ⭐ | `engine/strategies.py` EXPAND | `StrategyRecommendations` | אסטרטגיות אופציות + בחירה לפי regime |
| **LENS** | `engine/technicals.py` MINOR | `TechnicalSignal` | RSI/MACD/Bollinger, confidence ≤ MAX |

## Layer 3 — Risk & Suitability
| Agent | קובץ | Contract | תפקיד |
|-------|------|----------|-------|
| **GUARDIAN** ⭐ | `engine/guardian.py` NEW | `RiskAssessment` | Kelly Criterion + position sizing |
| **COMPASS** | `engine/compass.py` NEW | `SuitabilityReport` | סינון אסטרטגיות לפי פרופיל לקוח |
| **SCOUT** | `engine/scout.py` NEW | `CompetitiveInsights` | השוואה לכלים מוסדיים (לslide 9) |

## Layer 4 — Output (תמיד אחרון)
| Agent | קובץ | Contract | תפקיד |
|-------|------|----------|-------|
| **CLARITY** ⭐ | `engine/clarity.py` NEW | `ExplanationBundle` | 3 שכבות: יועץ / לקוח / רגולטור |
| **CANVAS** | `engine/canvas.py` NEW | HTML/PDF string | מצגת 10 שקפים (RTL עברית) |

## Flow בין הסוכנים
```
User → ATLAS
  ├── VERIFY (gate — אם נכשל: stop)
  ├── [parallel] KEYNES + RADAR + MIKI
  ├── SIGMA (needs: regime from KEYNES, events from RADAR)
  ├── MAX (validates SIGMA's preferred strategy)
  ├── GUARDIAN (needs: BacktestResult from MAX)
  ├── LENS (confidence = min(LENS_raw, MAX.confidence))
  ├── COMPASS (filters SIGMA's list by client profile)
  ├── SCOUT (competitive context for slide 9)
  ├── CLARITY (reads full package → 3 explanations)
  └── CANVAS (reads explanation → 10 slides)
```

## חוקי flow
1. VERIFY תמיד ראשון — כישלון → abort מיד
2. KEYNES + RADAR + MIKI = במקביל (asyncio.gather)
3. SIGMA רץ רק אחרי KEYNES (צריך regime)
4. MAX רץ רק על האסטרטגיה שSIGMA בחר (לא על כולן)
5. CANVAS תמיד אחרון
