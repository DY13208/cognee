"use client";

import { use } from "react";
import OntologyDetailPage from "./OntologyDetailPage";

export default function Page({ params }: { params: Promise<{ key: string }> }) {
  const { key } = use(params);
  return <OntologyDetailPage ontologyKey={decodeURIComponent(key)} />;
}
