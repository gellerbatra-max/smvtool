// types.ts -- TypeScript mirrors of backend/app/schemas.py Pydantic models.
// Every field here corresponds 1:1 to a real API response field; nothing is
// invented client-side, and no numeric constant is hardcoded (SMVs/costs/
// etc. are always read from these response shapes, never computed locally).

export type Role = "ie_engineer" | "viewer" | "administrator";

export interface Token {
  access_token: string;
  token_type: string;
  role: Role;
  username: string;
}

export interface UserOut {
  id: string;
  username: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface UserCreate {
  username: string;
  full_name: string;
  role: Role;
  password: string;
}

// ------------------------------------------------------------- styles ----

export type StepKind = "handling" | "bundle" | "seam" | "cycle";

// Step dicts are intentionally typed loosely (Record<string, unknown>) --
// the exact per-kind field set lives in the engine's smv_assembly.py step
// grammar, which this app must never re-encode or duplicate. The UI reads
// `kind` to pick a specialised sub-editor and passes every other field
// through untouched.
export interface StepDict {
  kind: StepKind;
  element?: string;
  machine_class?: string;
  path_length_mm?: number;
  spi?: number;
  curvature_class?: string;
  guidance_class?: string;
  plies?: number;
  pivots?: number;
  attachment?: string | null;
  params?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface OperationIn {
  name: string;
  sequence: number;
  bundle_size: number;
  steps: StepDict[];
}

export interface OperationOut extends OperationIn {
  id: string;
  style_id: string;
  created_at: string;
  updated_at: string;
}

export interface StyleCreate {
  name: string;
  garment_type?: string;
  variant?: string;
  size?: string;
  bundle_size?: number;
  notes?: string | null;
  seed_from_library?: boolean;
}

export interface StyleUpdate {
  name?: string;
  variant?: string;
  size?: string;
  bundle_size?: number;
  notes?: string | null;
}

export interface StyleOut {
  id: string;
  name: string;
  garment_type: string;
  variant: string;
  size: string;
  bundle_size: number;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface StyleDetailOut extends StyleOut {
  operations: OperationOut[];
}

// ------------------------------------------------------------ compute ----

export interface ComputeRequest {
  allowance_profile?: string;
  allowance_policy_id?: string | null;
}

export interface SMVResultOut {
  id: string;
  operation_id: string;
  style_id: string;
  st_op_s: number;
  st_op_min: number;
  bt_op_s: number;
  bt_op_min: number;
  allowance_profile: string;
  engine_version: string;
  calibration_version?: string | null;
  computed_at: string;
}

export interface ComputeResponse {
  style_id: string;
  smv_min: number;
  smv_tmu: number;
  bt_style_min: number;
  allowance_profile: string;
  engine_version: string;
  warnings: string[];
  results: SMVResultOut[];
}

// AuditTrail is the raw, unabridged assemble_operation() output -- shape is
// engine-defined and evolves with the engine, so it is typed as an open
// record here; the UI renders it generically (key/value + nested step
// records) rather than assuming specific fields.
export type AuditTrail = Record<string, unknown>;

export interface BulletinLatestResult {
  id: string;
  st_op_s: number;
  st_op_min: number;
  bt_op_s: number;
  bt_op_min: number;
  allowance_profile: string;
  engine_version: string;
  computed_at: string;
  audit_trail: AuditTrail;
}

export interface BulletinOperation {
  operation_id: string;
  name: string;
  sequence: number;
  bundle_size: number;
  latest_result: BulletinLatestResult | null;
}

export interface BulletinOut {
  style: StyleOut;
  operations: BulletinOperation[];
  smv_min: number | null;
  smv_tmu: number | null;
}

// ------------------------------------------------------------ audit log ---

export interface ChangeLogOut {
  id: string;
  entity_type: string;
  entity_id: string;
  style_id?: string | null;
  user_id?: string | null;
  timestamp: string;
  action: string;
  field: string;
  prior_value?: string | null;
  new_value?: string | null;
}

// --------------------------------------------------------- allowance ------

export interface AllowancePolicyOut {
  id: string;
  policy_name: string;
  version: number;
  is_active: boolean;
  created_at: string;
}

// ----------------------------------------------------------- library ------

export interface LibraryCatalog {
  variants: string[];
  sizes: string[];
  default_bundle_size: number;
  seam_operations: string[];
  cycle_operations: string[];
}

export interface LibraryBulletinOperation {
  // Passthrough of smv_assembly.assemble_operation()'s return dict, not a
  // dedicated Pydantic schema on the backend -- keys confirmed against a
  // live response, not guessed (see the "operation" vs "operation_name"/
  // "name" bug this replaced).
  operation: string;
  bundle_size: number;
  allowance_profile: string;
  BT_op_s: number;
  ST_op_s: number;
  BT_op_min: number;
  ST_op_min: number;
  no_double_count_warnings: string[];
  steps: unknown[];
}

export interface LibraryBulletin {
  size: string;
  variant: string;
  bundle_size: number;
  allowance_profile: string;
  smv_min: number;
  smv_tmu: number;
  engine_version: string;
  operations: LibraryBulletinOperation[];
  warnings: string[];
}

// -------------------------------------------------------- calibration ----

export interface CalibrationSymbol {
  scope: string;
  symbol: string;
  name?: string | null;
  units?: string | null;
  default?: unknown;
  status?: string | null;
  source?: string | null;
}

export interface CalibrationStatus {
  engine_version: string;
  taxonomy_version: string;
  n_symbols: number;
  n_calibration_pending: number;
  n_literature_grounded_or_fitted: number;
  symbols: CalibrationSymbol[];
  real_factory_calibration_run: boolean;
  note: string;
}

// ------------------------------------------------------------ analytics ----

export interface LineBalanceRequest {
  allowance_profile?: string;
  n_workstations?: number | null;
  target_rate_per_hour?: number | null;
  target_rate_per_day?: number | null;
  shift_hours?: number;
}

// LineBalanceOut has `extra="allow"` server-side, so this interface covers
// the documented fields and allows any additional ones through.
export interface LineBalanceOut {
  method: string;
  n_operations: number;
  total_smv_min: number;
  bottleneck_workstation: number;
  bottleneck_smv_min: number;
  theoretical_efficiency: number;
  n_workstations_used?: number;
  total_idle_min?: number;
  achievable_output_per_hour?: number;
  achievable_efficiency_at_target?: number;
  meets_target?: boolean;
  assignment?: Record<string, number>;
  workstations?: Array<{
    workstation: number;
    operations: string[];
    load_min: number;
    idle_min: number;
  }>;
  [key: string]: unknown;
}

export interface CostingRequest {
  allowance_profile?: string;
  labour_rate_per_hour: number;
  efficiency?: number;
  n_operators?: number | null;
  target_output_per_hour?: number | null;
  target_output_per_day?: number | null;
  shift_hours?: number;
}

export interface CostingReport {
  smv_min: number;
  labour_rate_per_hour: number;
  efficiency: number;
  cost_per_garment: number;
  production_at_n_operators?: {
    smv_min: number;
    n_operators: number;
    efficiency: number;
    output_per_hour: number;
    output_per_shift: number;
    output_per_day: number;
  };
  daily_labour_cost_at_n_operators?: number;
  required_operators_for_target?: {
    smv_min: number;
    target_output_per_hour: number;
    efficiency: number;
    operators_required_raw: number;
    operators_required: number;
  };
  target_output_per_hour?: number;
  target_output_per_day?: number;
  [key: string]: unknown;
}

export interface WhatIfRequest {
  allowance_profile?: string;
  operation_name: string;
  changes: Record<string, unknown>;
  step_kind?: string | null;
  element?: string | null;
  step_index?: number | null;
  match?: string;
  n_workstations?: number | null;
  target_rate_per_hour?: number | null;
  labour_rate_per_hour?: number | null;
  line_efficiency?: number;
}

export interface WhatIfResult {
  operation_name: string;
  change: Record<string, unknown>;
  operation_delta: Record<string, unknown>;
  base_style_smv_min: number;
  modified_style_smv_min: number;
  style_smv_delta_min: number;
  style_smv_delta_pct: number;
  line_balance?: { base: LineBalanceOut; modified: LineBalanceOut };
  bottleneck_change?: Record<string, unknown>;
  efficiency_delta?: Record<string, unknown>;
  costing?: { base: CostingReport; modified: CostingReport };
  cost_delta_per_garment?: number;
  [key: string]: unknown;
}
