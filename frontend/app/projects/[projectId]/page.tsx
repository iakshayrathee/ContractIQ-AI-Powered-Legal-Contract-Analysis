"use client";

import { useRef, useState, useEffect } from "react";
import { useProject } from "@/lib/hooks/useProjectQueries";
import { projectsApi } from "@/lib/api";
import type { Project } from "@/lib/types";
import ChatPanel from "@/components/chat/ChatPanel";
import KnowledgeBase from "@/components/project/KnowledgeBase";
import ContractAnalysisPanel from "@/components/contract/ContractAnalysisPanel";
import RiskDashboard from "@/components/contract/RiskDashboard";
import PlainSummaryPanel from "@/components/contract/PlainSummaryPanel";
import { Spinner } from "@/components/ui/Spinner";
import { MessageSquare, FileSearch, ShieldAlert, FileText, Layers, X, SidebarClose, SidebarOpen } from "lucide-react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";

interface Props {
  params: { projectId: string };
}

const TABS = [
  { key: "chat", label: "Chat", icon: MessageSquare },
  { key: "analysis", label: "Analysis", icon: FileSearch },
  { key: "risks", label: "Risks", icon: ShieldAlert },
  { key: "summary", label: "Summary", icon: FileText },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function ProjectPage({ params }: Props) {
  const { projectId } = params;
  const projectName = decodeURIComponent(projectId);
  
  const router = useRouter();
  const searchParams = useSearchParams();
  const pathname = usePathname();

  const activeTab = (searchParams.get("tab") as TabKey) || "chat";
  const [kbOpen, setKbOpen] = useState(false);
  const [kbCollapsed, setKbCollapsed] = useState(false);
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const { data: project, isLoading, error } = useProject(projectName);

  const hasDocuments = project ? project.document_count > 0 : false;
  const resolvedTab = !hasDocuments ? "chat" : activeTab;

  const setActiveTab = (tab: TabKey) => {
    if (tab !== "chat" && !hasDocuments) return;
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", tab);
    router.replace(`${pathname}?${params.toString()}`);
  };

  // Warning when leaving page with active chat drafts
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      const storageKey = `chatDrafts:${projectName}`;
      const draft = localStorage.getItem(storageKey);
      if (draft) {
        try {
          const parsed = JSON.parse(draft);
          if (parsed && parsed.length > 0) {
            e.preventDefault();
            e.returnValue = "You have unsaved changes in your chat draft. Are you sure you want to leave?";
            return e.returnValue;
          }
        } catch {}
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [projectName]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner />
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-muted text-sm">Project not found.</p>
      </div>
    );
  }

  const handleTabKeyDown = (e: React.KeyboardEvent, currentIndex: number) => {
    if (!hasDocuments) return;
    let nextIndex = currentIndex;
    if (e.key === "ArrowRight") nextIndex = (currentIndex + 1) % TABS.length;
    else if (e.key === "ArrowLeft") nextIndex = (currentIndex - 1 + TABS.length) % TABS.length;
    else if (e.key === "Home") nextIndex = 0;
    else if (e.key === "End") nextIndex = TABS.length - 1;
    else return;
    e.preventDefault();
    const nextKey = TABS[nextIndex].key;
    setActiveTab(nextKey);
    tabRefs.current[nextKey]?.focus();
  };

  return (
    <div className="flex flex-col lg:flex-row h-full">
      {/* Main content area with tabs */}
      <div className="flex-1 flex flex-col min-h-0">
        {/* Tab bar */}
        <div className="flex items-center gap-1 px-2 sm:px-5 border-b border-border bg-surface/50 relative overflow-x-auto">
          {/* Gold shimmer bottom line */}
          <div className="absolute bottom-0 left-0 right-0 h-px gold-line opacity-60" />
          <div role="tablist" aria-label="Project sections" className="flex items-center gap-1 flex-1 py-2 min-w-min">
            {TABS.map(({ key, label, icon: Icon }, index) => {
              const isDisabled = key !== "chat" && !hasDocuments;
              return (
                <button
                  key={key}
                  ref={(el) => { tabRefs.current[key] = el; }}
                  role="tab"
                  id={`tab-${key}`}
                  aria-selected={resolvedTab === key}
                  aria-controls={`panel-${key}`}
                  tabIndex={resolvedTab === key ? 0 : -1}
                  disabled={isDisabled}
                  onClick={() => !isDisabled && setActiveTab(key)}
                  onKeyDown={(e) => handleTabKeyDown(e, index)}
                  className={`relative flex items-center gap-2 px-3 sm:px-4 py-2.5 rounded-xl text-xs font-medium transition-all duration-200 min-h-[44px] sm:min-h-auto focus-ring
                    ${resolvedTab === key && !isDisabled
                      ? "bg-gold/[0.10] text-gold border border-gold/25 shadow-glow-sm"
                      : "text-muted hover:text-white hover:bg-white/[0.04]"
                    }
                    ${isDisabled ? "opacity-40 cursor-not-allowed hover:bg-transparent hover:text-muted" : ""}
                  `}
                >
                  <Icon className={`w-4 h-4 sm:w-3.5 sm:h-3.5 shrink-0 ${resolvedTab === key && !isDisabled ? "text-gold" : ""}`} />
                  <span className="hidden sm:inline whitespace-nowrap">{label}</span>
                </button>
              );
            })}
          </div>

          {/* Desktop KB Collapse Toggle Button */}
          <button
            onClick={() => setKbCollapsed(!kbCollapsed)}
            aria-label={kbCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="hidden lg:flex items-center justify-center w-10 h-10 rounded-xl text-xs text-muted hover:text-gold hover:bg-gold/[0.06] transition-colors shrink-0 focus-ring mr-2"
          >
            {kbCollapsed ? (
              <SidebarOpen className="w-4 h-4" />
            ) : (
              <SidebarClose className="w-4 h-4" />
            )}
          </button>

          {/* Mobile KB toggle */}
          <button
            onClick={() => setKbOpen(true)}
            aria-label="Open knowledge base"
            className="lg:hidden flex items-center justify-center w-10 h-10 sm:w-auto sm:h-auto sm:gap-1.5 sm:px-3 sm:py-2 rounded-xl text-xs text-muted hover:text-gold hover:bg-gold/[0.06] transition-colors shrink-0 focus-ring"
          >
            <Layers className="w-4 h-4 sm:w-3.5 sm:h-3.5" />
            <span className="hidden sm:inline whitespace-nowrap">KB</span>
          </button>
        </div>

        {/* Tab panels */}
        <div
          role="tabpanel"
          id={`panel-${resolvedTab}`}
          aria-labelledby={`tab-${resolvedTab}`}
          className="flex-1 flex flex-col min-h-0"
        >
          {resolvedTab === "chat" && <ChatPanel project={project} />}
          {resolvedTab === "analysis" && <ContractAnalysisPanel project={project} />}
          {resolvedTab === "risks" && (
            <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-6">
              <RiskDashboard project={project} />
            </div>
          )}
          {resolvedTab === "summary" && (
            <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-6">
              <PlainSummaryPanel project={project} />
            </div>
          )}
        </div>
      </div>

      {/* Desktop Knowledge Base sidebar */}
      <div className={`hidden lg:flex transition-all duration-300 overflow-hidden ${
        kbCollapsed ? "w-0 border-l-0" : "w-80 border-l border-border"
      }`}>
        <div className="w-80">
          <KnowledgeBase project={project} />
        </div>
      </div>

      {/* Mobile Knowledge Base sheet */}
      {kbOpen && (
        <div
          className="lg:hidden fixed inset-0 z-50 flex items-stretch justify-end"
          role="dialog"
          aria-modal="true"
          aria-label="Knowledge base"
        >
          <div
            className="absolute inset-0 bg-primary/70 backdrop-blur-sm fade-in"
            onClick={() => setKbOpen(false)}
          />
          <div className="relative z-10 w-80 max-w-[90vw] flex slide-in-from-right-5">
            <div className="absolute top-3 right-3 z-20">
              <button
                onClick={() => setKbOpen(false)}
                aria-label="Close knowledge base"
                className="w-8 h-8 flex items-center justify-center rounded-lg bg-card border border-border text-muted hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <KnowledgeBase project={project} />
          </div>
        </div>
      )}
    </div>
  );
}
