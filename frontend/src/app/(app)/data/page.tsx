import type { Metadata } from "next";
import { Suspense } from "react";

import { DataLab } from "@/features/data/data-lab";

export const metadata: Metadata = { title: "Data Lab" };

export default function DataPage() {
  return (
    <Suspense>
      <DataLab />
    </Suspense>
  );
}
