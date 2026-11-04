"use client";

import * as React from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { cn } from "@/lib/utils";

const LABEL = /\[((?:S|D)\d+)\]/g;

/** Turn evidence labels like [S2] into links so they render as interactive citation chips. */
export function linkifyCitations(md: string): string {
  // Leave fenced code untouched.
  return md
    .split(/(```[\s\S]*?```)/g)
    .map((part) => (part.startsWith("```") ? part : part.replace(LABEL, (_, l) => `[${l}](#cite-${l})`)))
    .join("");
}

export function Markdown({
  content,
  streaming,
  onCite,
  known,
  className,
}: {
  content: string;
  streaming?: boolean;
  onCite?: (label: string) => void;
  known?: Set<string>;
  className?: string;
}) {
  const md = React.useMemo(() => linkifyCitations(content), [content]);
  return (
    <div className={cn("nx-prose", streaming && "nx-streaming", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex, [rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith("#cite-")) {
              const label = href.slice(6);
              const ok = !known || known.has(label);
              return (
                <button
                  type="button"
                  onClick={() => onCite?.(label)}
                  className={cn(
                    "mx-0.5 inline-flex h-[18px] -translate-y-px items-center rounded-md px-1.5 align-middle font-mono text-[10.5px] font-semibold no-underline transition",
                    label.startsWith("D")
                      ? "bg-[#f5f3ff] text-violet hover:bg-[#ede9fe]"
                      : ok
                        ? "bg-primary-soft text-primary-deep hover:bg-[#dbe7ff]"
                        : "bg-surface-2 text-faint line-through",
                  )}
                  aria-label={`Citation ${label}`}
                >
                  {label}
                </button>
              );
            }
            return (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            );
          },
        }}
      >
        {md}
      </ReactMarkdown>
      {streaming && !content && <span className="nx-caret text-faint" />}
    </div>
  );
}
