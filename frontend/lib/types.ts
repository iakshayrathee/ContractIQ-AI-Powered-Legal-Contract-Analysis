// Types mirroring backend Pydantic schemas

export interface Project {
  name: string;
  description: string;
  collection_name: string;
  created_at: string;
  document_count: number;
}

export interface JobStep {
  name: string;
  status: "pending" | "running" | "completed" | "failed";
  started_at: string | null;
  completed_at: string | null;
  details: Record<string, unknown> | null;
}

export interface Job {
  job_id: string;
  project_name: string;
  document_name: string;
  status: "pending" | "running" | "completed" | "failed";
  steps: JobStep[];
  chunk_count: number | null;
  error: string | null;
  created_at: string;
}

export interface IngestJobResponse {
  job_id: string;
  message: string;
  project_name: string;
  document_name: string;
}

export interface ChunkItem {
  chunk_id: string;
  content: string;
  content_types: string[];
  raw_text: string;
  tables_html: string[];
  images_base64: string[];
  source_file?: string;
  // Rich metadata fields
  page_number?: number;
  chunk_index?: number;
  clause_type?: string;
  chunk_type?: string;
  source_type?: string;
  section_reference?: string;
  image_dimensions?: string;
}

export interface ChunksResponse {
  project_name: string;
  total: number;
  chunks: ChunkItem[];
}

export interface SourceChunk {
  content: string;
  raw_text: string;
  tables_html: string[];
  images_base64: string[];
  content_types: string[];
  page_numbers: number[];
  source_file?: string;
  relevance_score?: number;
}

export interface QueryResponse {
  question: string;
  answer: string;
  chunks_retrieved: number;
  project_name: string;
  sources: SourceChunk[];
}

export interface HealthResponse {
  status: string;
  version: string;
  vectorstore_loaded: boolean;
  qdrant_url: string | null;
  collection_document_count: number | null;
}

// ---------------------------------------------------------------------------
// Contract Analysis
// ---------------------------------------------------------------------------

export interface Obligation {
  party: string;
  description: string;
  deadline: string | null;
  type: "must" | "must_not" | "may";
}

export interface ContractClause {
  clause_type: string;
  title: string;
  text: string;
  section_reference: string | null;
  obligations: Obligation[];
}

export interface ContractMetadata {
  contract_type: string;
  parties: string[];
  effective_date: string | null;
  expiration_date: string | null;
  governing_law: string | null;
  jurisdiction: string | null;
}

export interface ContractAnalysis {
  metadata: ContractMetadata;
  clauses: ContractClause[];
  key_dates: string[];
  summary: string;
}

export interface AnalysisResponse {
  project_name: string;
  status: "none" | "pending" | "running" | "completed" | "failed";
  analysis: ContractAnalysis | null;
  risk_report: RiskReport | null;
  summary: PlainSummary | null;
  /** WS-2.2: pipeline stage for progress display while status="running" */
  stage?: {
    stage: "extracting_clauses" | "assessing_risk" | "writing_summary" | "reviewing_quality" | "completed" | "failed";
    processed?: number;
    total?: number;
  } | null;
}

// ---------------------------------------------------------------------------
// Risk Analysis
// ---------------------------------------------------------------------------

export interface RiskItem {
  category: string;
  severity: "low" | "medium" | "high" | "critical";
  title: string;
  description: string;
  clause_reference: string | null;
  recommendation: string;
}

export interface RiskReport {
  overall_score: number;
  risk_level: string;
  items: RiskItem[];
  missing_clauses: string[];
  summary: string;
}

export interface RiskResponse {
  project_name: string;
  risk_report: RiskReport | null;
}

// ---------------------------------------------------------------------------
// Plain-English Summary
// ---------------------------------------------------------------------------

export interface PlainSummary {
  executive_summary: string;
  what_this_does: string;
  obligations_by_party: Record<string, string[]>;
  key_dates: string[];
  watch_out_for: string[];
  action_items: string[];
}

export interface SummaryResponse {
  project_name: string;
  summary: PlainSummary | null;
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export interface DashboardTrends {
  projects: number | null;
  analyses: number | null;
  risk: number | null;
}

export interface TimelinePoint {
  date: string; // ISO date (YYYY-MM-DD)
  count: number;
}

export interface DashboardStats {
  total_projects: number;
  total_documents: number;
  total_analyses: number;
  avg_risk_score: number;
  high_risk_count: number;
  flagged_count: number;
  avg_quality_score: number;
  risk_distribution: Record<string, number>;
  clause_type_counts: Record<string, number>;
  risk_category_counts: Record<string, number>;
  contract_type_counts: Record<string, number>;
  analyses_timeline: TimelinePoint[];
  trends: DashboardTrends;
  recent_analyses: Array<{
    project_name: string;
    risk_score: number;
    status: string;
    created_at: string;
  }>;
  range: string;
}

export type DashboardRange = "7d" | "30d" | "90d" | "all";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  chunks_retrieved?: number;
  sources?: SourceChunk[];
  timestamp: Date;
}

/** Shape returned by GET /projects/{name}/chat */
export interface ChatMessageResponse {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: SourceChunk[];
  created_at: string;
}
