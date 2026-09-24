import { redirect } from "next/navigation";

/** Ontology management lives on the Brain dataset page; sidebar now opens Teleology. */
export default function OntologiesRedirect() {
  redirect("/teleology");
}
