import { Badge } from "@/components/ui/badge";
import { jobStatusLabel } from "@/lib/format";

const variant: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  queued: "outline",
  running: "default",
  succeeded: "secondary",
  failed: "destructive",
  dead: "destructive",
  cancelled: "outline",
};

export function JobStatusBadge({ status }: { status: string }) {
  return <Badge variant={variant[status] ?? "outline"}>{jobStatusLabel[status] ?? status}</Badge>;
}
