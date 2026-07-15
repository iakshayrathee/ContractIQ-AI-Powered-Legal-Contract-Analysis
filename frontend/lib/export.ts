/**
 * Export utilities for ContractIQ
 * Supports PDF and CSV exports
 */

export interface ExportOptions {
  filename: string;
  format: "pdf" | "csv";
}

/**
 * Export analysis data to CSV
 */
export function exportToCSV(
  data: Record<string, unknown>[],
  filename: string
): void {
  if (!data || data.length === 0) return;

  // Get headers from first object
  const headers = Object.keys(data[0]);

  // Create CSV content
  const csvContent = [
    headers.join(","),
    ...data.map((row) =>
      headers
        .map((header) => {
          const value = row[header];
          // Escape quotes and wrap in quotes if contains comma
          if (typeof value === "string" && (value.includes(",") || value.includes('"'))) {
            return `"${value.replace(/"/g, '""')}"`;
          }
          return value ?? "";
        })
        .join(",")
    ),
  ].join("\n");

  // Create blob and download
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  downloadBlob(blob, `${filename}.csv`);
}

/**
 * Export analysis summary to text
 */
export function exportToText(
  content: string,
  filename: string
): void {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8;" });
  downloadBlob(blob, `${filename}.txt`);
}

/**
 * Export conversation history
 */
export function exportConversation(
  messages: Array<{ role: string; content: string; timestamp: Date }>,
  projectName: string
): void {
  const content = messages
    .map(
      (msg) =>
        `[${msg.timestamp.toLocaleTimeString()}] ${msg.role.toUpperCase()}:\n${msg.content}`
    )
    .join("\n\n---\n\n");

  exportToText(content, `${projectName}-conversation`);
}

/**
 * Helper to trigger download
 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Generate analysis report as formatted text
 */
export function generateAnalysisReport(data: {
  projectName: string;
  riskScore: number;
  riskLevel: string;
  summary: string;
  clauses: Array<{ title: string; type: string }>;
  missingClauses: string[];
  actionItems: string[];
}): string {
  const lines = [
    `CONTRACT ANALYSIS REPORT`,
    `Project: ${data.projectName}`,
    `Generated: ${new Date().toLocaleString()}`,
    ``,
    `RISK ASSESSMENT`,
    `Overall Risk Score: ${data.riskScore}/100`,
    `Risk Level: ${data.riskLevel.toUpperCase()}`,
    ``,
    `SUMMARY`,
    data.summary,
    ``,
    `CLAUSES EXTRACTED (${data.clauses.length})`,
    ...data.clauses.map((c) => `- ${c.title} (${c.type})`),
    ``,
    `MISSING CLAUSES (${data.missingClauses.length})`,
    ...data.missingClauses.map((c) => `- ${c}`),
    ``,
    `ACTION ITEMS (${data.actionItems.length})`,
    ...data.actionItems.map((item) => `- ${item}`),
  ];

  return lines.join("\n");
}
