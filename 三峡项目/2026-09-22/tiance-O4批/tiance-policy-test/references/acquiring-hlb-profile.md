# HLB Acquiring Project Profile

Version: 1.0.0

This document defines project-specific configurations for HLB (Hong Leong Bank) acquiring risk control rules.

## Fixed Public Fields

All test cases for HLB acquiring must include these fixed fields:

```json
{
  "S_S_APPCODE": "Acquiring",
  "S_S_PARTNERCODE": "kratos",
  "S_S_ORGCODE": "hlb_my"
}
```

## Interface Addresses and Event Type Mapping

| Event Type | Interface Address | Encoding |
|---|---|---|
| AcqAuthorization | http://<HLB_HOST>:8000/riskService/trade/riskDecision/acqAuthorization | application/json |
| AcqModify | http://<HLB_HOST>:8000/indexApi/salaxyService/acqModify/metric | application/x-www-form-urlencoded |
| AcqDisputes | http://<HLB_HOST>:8000/indexApi/salaxyService/acqDisputes/metric | application/x-www-form-urlencoded |

**Important**:
- AcqAuthorization uses JSON encoding
- AcqModify and AcqDisputes use form encoding (application/x-www-form-urlencoded)

## Field Mappings

### AcqAuthorization Interface

| Interface Field | System Field Code | Type | Required | Notes |
|---|---|---|---|---|
| bizid | S_S_BIZID | string | Yes | Unique transaction ID |
| biztime | S_D_BIZTIME | timestamp | Yes | ISO8601 format |
| transactionamount | C_F_TRANSACTIONAMOUNT | number | Yes | Transaction amount |
| merchantid | C_S_MERCHANTID | string | Yes | Merchant ID |
| merchantname | C_S_MERCHANTNAME | string | Yes | Merchant name |
| mcc | C_S_MCC | string | Yes | Merchant category code |
| posentrymode | C_E_POSENTRYMODE | enum | Yes | POS entry mode (C/K/E) |
| transactiontype | C_E_TRANSACTIONTYPE | enum | Yes | Transaction type (M/B/U/P) |
| terminalid | C_S_TERMINALID | string | Yes | Terminal ID |
| customeracctnumber | C_S_CUSTOMERACCTNUMBER | string | Yes | Customer account number |
| paymentinstrumentid | C_S_PAYMENTINSTRUMENTID | string | Yes | Payment instrument ID |
| userdata01 | C_S_USERDATA01 | string | No | Custom field |
| userdata02 | C_E_CARDSCHEME | enum | No | Card scheme (V/M) |
| userdata03 | C_E_TXNSTATUSCODE | enum | No | Transaction status code (1/2) |
| userdata12 | C_F_ORIGINALTRXNAMOUNT | number | No | Original transaction amount |

### AcqModify Interface

| Interface Field | System Field Code | Type | Required | Notes |
|---|---|---|---|---|
| bizid | S_S_BIZID | string | Yes | Unique transaction ID |
| biztime | S_D_BIZTIME | timestamp | Yes | ISO8601 format |
| merchantid | C_S_MERCHANTID | string | Yes | Merchant ID |
| mcc | C_S_MCC | string | Yes | Merchant category code |
| userdata12 | C_F_TRANSACTIONAMOUNT | number | Yes | **Note**: Maps to TRANSACTIONAMOUNT, not ORIGINALTRXNAMOUNT |

### AcqDisputes Interface

| Interface Field | System Field Code | Type | Required | Notes |
|---|---|---|---|---|
| bizid | S_S_BIZID | string | Yes | Unique transaction ID |
| biztime | S_D_BIZTIME | timestamp | Yes | ISO8601 format |
| merchantid | C_S_MERCHANTID | string | Yes | Merchant ID |
| mcc | C_S_MCC | string | Yes | Merchant category code |
| userdata12 | C_F_TRANSACTIONAMOUNT | number | Yes | **Note**: Maps to TRANSACTIONAMOUNT, not ORIGINALTRXNAMOUNT |

## Valid Enum Values

### C_E_CARDSCHEME (Card Scheme)
- `V` - Visa
- `M` - MasterCard

**Invalid values**: VISA, Mastercard, VISA_CARD (these will cause enum validation errors)

### C_E_TXNSTATUSCODE (Transaction Status Code)
- `1` - Normal
- `2` - Reversal

**Invalid values**: Any other values will cause enum validation errors

### C_E_POSENTRYMODE (POS Entry Mode)
- `C` - Chip (EMV)
- `K` - Manual entry (keyed)
- `E` - E-commerce (CNP)

### C_E_TRANSACTIONTYPE (Transaction Type)
- `M` - Purchase
- `B` - Cash advance
- `U` - Account funding
- `P` - Prepaid load
- `R` - Refund
- `X` - Refund-related transaction type used by HLB refund rules

## Bank Card Number Field Differences

Different interfaces use different field names for bank card numbers:

| Interface | Field Name | System Field Code |
|---|---|---|
| AcqAuthorization | paymentinstrumentid | C_S_PAYMENTINSTRUMENTID |
| AcqModify | (not applicable) | - |
| AcqDisputes | (not applicable) | - |

**Important**: Only AcqAuthorization requires the paymentinstrumentid field. AcqModify and AcqDisputes do not include card numbers.

## Time Window Rules

### Standard Time Windows
- "近1天" = within 24 hours before current biztime
- "近24小时" = within 24 hours before current biztime
- "近7天" = within 7 days before current biztime
- "近90天" = within 90 days before current biztime

### Special Time Windows
- "90天剔除3天" = within 90 days, excluding the most recent 3 days
- "24小时剔除3天" = within 24 hours, excluding the most recent 3 days

## Indicator Count Planning

Confirm whether each platform indicator includes the current transaction before deciding the history count. The table below applies only when the current transaction is excluded.

| Condition Pattern | Historical Transaction Count |
|---|---|
| 近1天交易笔数 >= N | N transactions |
| 近24小时交易笔数 >= N | N transactions |
| 近7天交易笔数 >= N | N transactions |
| 近90天交易笔数 >= N | N transactions |

**Example**: If condition says "近1天交易笔数 >= 10", construct exactly 10 historical transactions.

## Metric-Window Settle (Materialization Wait)

After all historical transactions are accepted and before the current transaction is
submitted, the runner pauses so the platform can materialize the sliding-window
indicators. This wait is now derived per case from the contract's own indicator
window (O4), instead of a single global fixed delay:

- **Auto (default)**: read each expected indicator's window suffix (`_5m`, `_2h`,
  `_1d`, …); take the slowest (max) window across the case's indicators, since the
  wait runs after all history. For sliding windows, `settle = clamp(window × factor,
  floorSeconds, capSeconds)`; for windows ≥ 1 day (natural-day aggregation) use
  `naturalDaySeconds`; if no indicator carries a window suffix, fall back to
  `defaultSeconds`.
- **Override**: `--settle <seconds>` forces one fixed wait for every case (old
  behavior); `--settle auto` restores the per-case derivation.
- **Tuning**: all parameters live under `acquiring.settle` in `config.json`
  (`defaultSeconds`, `factor`, `floorSeconds`, `capSeconds`, `naturalDaySeconds`) —
  adjust for environments with slower/faster materialization without editing code.
- **Audit**: the chosen wait and its basis (`cli` / `auto` / `fallback`) are archived
  in each case's `result.json` (`settle` field) and, for `--dry-run`, in
  `planned_requests.json`.

Rationale: a global dead-wait is simultaneously too long for fast cases and too
short for slow ones. Deriving it from the contract keeps each case just long enough
while making the decision explicit and reproducible.

## Isolation Convention

Use format `M{row_number}` for merchant IDs:
- Row 116 → M116
- Row 117 → M117
- Row 118 → M118

For multiple merchants in the same test case, use suffixes:
- M116_1, M116_2, M116_3

Also isolate every key used by the indicator, including card/account, terminal, customer/CIF, and MIDBIN. Do not run cases concurrently when any relevant key is shared.

## Known Issues

### Issue 1: Field Mapping Mismatch
- **Problem**: userdata12 in AcqModify/AcqDisputes maps to C_F_TRANSACTIONAMOUNT, not C_F_ORIGINALTRXNAMOUNT
- **Impact**: Chargeback ratio metrics will be incorrect if using ORIGINALTRXNAMOUNT
- **Solution**: Use TRANSACTIONAMOUNT for AcqModify/AcqDisputes interfaces

### Issue 2: Enum Value Mismatch
- **Problem**: Card scheme enum only accepts V/M, not VISA/MasterCard
- **Impact**: Test data with VISA/MasterCard will fail enum validation
- **Solution**: Use V for Visa, M for MasterCard

### Issue 3: AcqAuthorization Encoding
- **Problem**: AcqAuthorization requires JSON encoding, not form encoding
- **Impact**: Test data with form encoding will fail
- **Solution**: Use application/json content-type for AcqAuthorization interface

## Validation Checklist

Before submitting test data, verify:

- [ ] All required fields present (per interface)
- [ ] Enum values are valid (V/M for card scheme, 1/2 for status code)
- [ ] Interface addresses match event type mapping
- [ ] Outbound requests use interface field names (`transactionamount`, not `C_F_TRANSACTIONAMOUNT`)
- [ ] Historical transaction count matches verified current-inclusion semantics
- [ ] Execution metadata identifies target rule, target rule set, strategy, and case type
- [ ] Expected current fields match the final serialized outbound request
- [ ] Isolation covers every relevant metric grouping key
- [ ] Timestamps are relative to current biztime
- [ ] Empty fields are deleted (not included in JSON)
- [ ] JSON length <= 32767 characters
- [ ] Bank card number field present for AcqAuthorization (paymentinstrumentid)
- [ ] AcqAuthorization uses JSON encoding
- [ ] AcqModify/AcqDisputes use form encoding
