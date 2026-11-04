"use client";

import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
import * as React from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";

import { Button } from "@/components/ui/button";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

/** Renders the stored PDF and opens at the cited page. */
export default function PdfViewer({ url, page, highlight }: { url: string; page: number; highlight?: string }) {
  const [current, setCurrent] = React.useState(page);
  const [pages, setPages] = React.useState(0);
  const [scale, setScale] = React.useState(1.1);
  const [prev, setPrev] = React.useState(page);
  if (prev !== page) {
    setPrev(page);
    setCurrent(page);
  }
  const words = React.useMemo(
    () => new Set((highlight ?? "").toLowerCase().split(/\W+/).filter((w) => w.length > 4).slice(0, 40)),
    [highlight],
  );

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1.5 border-b border-line bg-surface px-3 py-2">
        <Button variant="ghost" size="icon-sm" disabled={current <= 1} onClick={() => setCurrent((p) => p - 1)} aria-label="Previous page"><ChevronLeft /></Button>
        <span className="text-[12.5px] tabular-nums text-ink-2">Page {current} / {pages || "…"}</span>
        <Button variant="ghost" size="icon-sm" disabled={!pages || current >= pages} onClick={() => setCurrent((p) => p + 1)} aria-label="Next page"><ChevronRight /></Button>
        <div className="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="icon-sm" onClick={() => setScale((s) => Math.max(0.6, s - 0.15))} aria-label="Zoom out"><ZoomOut /></Button>
          <Button variant="ghost" size="icon-sm" onClick={() => setScale((s) => Math.min(2.2, s + 0.15))} aria-label="Zoom in"><ZoomIn /></Button>
        </div>
      </div>
      <div className="nx-scroll flex-1 overflow-auto bg-bg-subtle p-4">
        <Document file={url} onLoadSuccess={(d) => setPages(d.numPages)} options={{ withCredentials: true }} loading={<div className="p-6 text-[13px] text-muted">Loading PDF…</div>} error={<div className="p-6 text-[13px] text-danger">Could not render this PDF.</div>}>
          <div className="mx-auto w-fit overflow-hidden rounded-lg shadow-pop">
            <Page
              pageNumber={current}
              scale={scale}
              renderAnnotationLayer={false}
              customTextRenderer={({ str }) =>
                words.size && str.toLowerCase().split(/\W+/).some((w) => words.has(w)) ? `<mark style="background:rgb(250 204 21 / .45);color:inherit">${escape(str)}</mark>` : escape(str)
              }
            />
          </div>
        </Document>
      </div>
    </div>
  );
}

function escape(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}
