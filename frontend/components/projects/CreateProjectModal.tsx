"use client";

import { useState, useCallback } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { projectsApi } from "@/lib/api";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { AlertCircle } from "lucide-react";

interface Props {
  open: boolean;
  onClose: () => void;
}

const inputClass = `w-full bg-card border border-border rounded-xl px-3 py-2.5 text-sm
  text-white placeholder-muted focus:outline-none focus:ring-2 focus:ring-accent/20
  focus:border-accent/40 transition-all`;

export default function CreateProjectModal({ open, onClose }: Props) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  const mutation = useMutation({
    mutationFn: () => projectsApi.create(name.trim(), description.trim()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      toast(`Project "${name.trim()}" created`, "success");
      setName(""); setDescription(""); setError("");
      onClose();
    },
    onError: (err: Error) => setError(err.message),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) { setError("Project name is required."); return; }
    setError("");
    mutation.mutate();
  };

  const handleClose = useCallback(() => {
    setName(""); setDescription(""); setError("");
    onClose();
  }, [onClose]);

  return (
    <Modal open={open} onClose={handleClose} title="New project">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="project-name" className="block text-xs font-medium text-white/80 mb-1.5">
            Project name <span className="text-red-400">*</span>
          </label>
          <input
            id="project-name"
            autoFocus
            value={name}
            onChange={(e) => { setName(e.target.value); setError(""); }}
            placeholder="e.g. Research Papers"
            maxLength={80}
            className={inputClass}
          />
          <p className="text-xs text-subtle mt-1 text-right">{name.length}/80</p>
        </div>

        <div>
          <label htmlFor="project-desc" className="block text-xs font-medium text-white/80 mb-1.5">
            Description
            <span className="ml-1 text-muted font-normal">(optional)</span>
          </label>
          <textarea
            id="project-desc"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What documents will this project contain?"
            maxLength={500}
            className={`${inputClass} resize-none`}
          />
          <p className="text-xs text-subtle mt-1 text-right">{description.length}/500</p>
        </div>

        {error && (
          <div className="flex items-center gap-2 text-xs text-red-400 bg-red-950/40 border border-red-900/50 rounded-lg px-3 py-2.5">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="outline" size="sm" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" loading={mutation.isPending}>
            Create project
          </Button>
        </div>
      </form>
    </Modal>
  );
}
