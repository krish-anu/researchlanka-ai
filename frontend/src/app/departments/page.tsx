import Link from "next/link";
import { redirect } from "next/navigation";

import { PageIntro } from "@/components/layout/PageIntro";
import { ApiErrorPanel, EmptyState } from "@/components/ui/Feedback";
import { listDepartments } from "@/services/api";
import { formatNumber } from "@/services/format";
import { departmentHref } from "@/services/links";

export const metadata = {
  title: "Departments",
  description: "AI research portfolios for university departments, built from author affiliations.",
};

export default async function DepartmentsPage() {
  const result = await listDepartments();

  // A directory of one is a wasted click; it lists departments once there are several.
  if (result.ok && result.value.data.length === 1) {
    redirect(departmentHref(result.value.data[0].department_id));
  }

  return (
    <div className="flex flex-col gap-4">
      <PageIntro
        title="Departments"
        description="AI research portfolios for university departments. Departments are attributed from the affiliation each author wrote on a publication, so portfolios exist only for departments that have been configured."
      />
      {!result.ok ? (
        <ApiErrorPanel error={result.error} what="departments" />
      ) : result.value.data.length === 0 ? (
        <EmptyState title="No department portfolios have been built yet" />
      ) : (
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {result.value.data.map((department) => (
            <li key={department.department_id}>
              <Link
                href={departmentHref(department.department_id)}
                className="panel interactive-card block p-4"
              >
                <span className="block font-display text-h3 text-ink">{department.name}</span>
                <span className="mt-1 block text-body-sm text-ink-secondary">
                  {department.institution_name}
                  {department.faculty ? ` · ${department.faculty}` : ""}
                </span>
                <span className="mt-2 block text-body-sm text-muted">
                  {formatNumber(department.tagged_publication_count)} AI publications attributed
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
