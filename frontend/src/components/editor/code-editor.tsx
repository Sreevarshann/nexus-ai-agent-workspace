"use client";

import Editor, { loader } from "@monaco-editor/react";
import * as React from "react";

import { Skeleton } from "@/components/ui/feedback";

let configured = false;

/** Monaco bundled locally (no CDN), so the editor works fully offline. */
export default function CodeEditor({
  value,
  onChange,
  language,
  height = 220,
  onRun,
}: {
  value: string;
  onChange: (v: string) => void;
  language: "sql" | "markdown" | "json";
  height?: number | string;
  onRun?: () => void;
}) {
  const [ready, setReady] = React.useState(configured);
  React.useEffect(() => {
    if (configured) return;
    void import("monaco-editor").then((monaco) => {
      loader.config({ monaco });
      configured = true;
      setReady(true);
    });
  }, []);
  if (!ready) return <Skeleton className="w-full" />;
  return (
    <Editor
      height={height}
      language={language}
      value={value}
      onChange={(v) => onChange(v ?? "")}
      onMount={(editor, monaco) => {
        if (onRun) editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, onRun);
      }}
      options={{
        minimap: { enabled: false },
        fontSize: 13,
        fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
        lineNumbers: language === "markdown" ? "off" : "on",
        scrollBeyondLastLine: false,
        wordWrap: language === "markdown" ? "on" : "off",
        padding: { top: 10, bottom: 10 },
        renderLineHighlight: "none",
        overviewRulerLanes: 0,
        automaticLayout: true,
      }}
    />
  );
}
