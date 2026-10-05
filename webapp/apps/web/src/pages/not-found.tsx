import { Link } from "react-router";
import { PageHeader } from "@/components/layout";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <>
      <PageHeader title="Not found" description="There is no page at this address." />
      <Button asChild variant="outline"><Link to="/">Back to the dashboard</Link></Button>
    </>
  );
}
