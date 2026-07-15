"use client";

import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ingestApi } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { UploadCloud, AlertCircle } from "lucide-react";
import { Spinner } from "@/components/ui/Spinner";

interface Props {
  projectName: string;
  onJobStarted: (jobId: string) => void;
}

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

export default function UploadArea({ projectName, onJobStarted }: Props) {
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();

  const mutation = useMutation({
    mutationFn: (file: File) => ingestApi.ingest(projectName, file, false, (p) => setUploadProgress(p)),
    onSuccess: (data) => {
      setError("");
      setUploadProgress(0);
      toast(`Processing "${data.document_name}" started`, "info");
      onJobStarted(data.job_id);
    },
    onError: (err: Error) => {
      setError(err.message);
      setUploadProgress(0);
      toast(`Upload failed: ${err.message}`, "error");
    },
  });

  function handleFile(file: File) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are supported.");
      return;
    }
    if (file.size > MAX_FILE_SIZE) {
      setError(`File too large. Maximum size is ${MAX_FILE_SIZE / 1024 / 1024}MB.`);
      return;
    }
    setError("");
    mutation.mutate(file);
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  return (
    <div className="space-y-2">
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload PDF file — click or drag and drop"
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inputRef.current?.click(); } }}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-5 text-center cursor-pointer transition-all duration-200
          ${dragging
            ? "border-accent bg-accent/5 scale-[1.02]"
            : "border-border hover:border-accent/50 hover:bg-white/[0.02]"
          }
          ${mutation.isPending ? "pointer-events-none opacity-60" : ""}`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
        />
        {mutation.isPending ? (
          <div className="flex flex-col items-center gap-3">
            <Spinner size="sm" />
            <div className="text-center">
              <p className="text-xs text-muted font-medium">Uploading...</p>
              <div className="w-32 h-1.5 bg-card rounded-full overflow-hidden mt-2">
                <div
                  className="bg-gradient-gold h-full transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <p className="text-[10px] text-muted mt-1">{uploadProgress}%</p>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-1.5">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center mb-1 transition-colors
              ${dragging ? "bg-accent/15" : "bg-card border border-border"}`}>
              <UploadCloud className={`w-4.5 h-4.5 ${dragging ? "text-accent-light" : "text-muted"}`} />
            </div>
            <p className="text-sm font-medium text-white">Drop PDF here</p>
            <p className="text-xs text-muted">or click to browse</p>
            <p className="text-[10px] text-subtle mt-1">Max 50MB • PDF only</p>
          </div>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-1.5 text-xs text-red-400">
          <AlertCircle className="w-3 h-3 shrink-0" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
