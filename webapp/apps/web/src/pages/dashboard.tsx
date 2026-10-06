import { BotControlCard } from "@/components/bot-control";
import { AccountFilter, ErrorNote, useAccountParam } from "@/components/common";
import { PageHeader } from "@/components/layout";
import { OverviewSkeleton, OverviewView } from "@/components/overview";
import { accountLabel } from "@/lib/format";
import { useOverview } from "@/lib/queries";

export function DashboardPage() {
  const [account] = useAccountParam();
  const overview = useOverview(account);
  return (
    <>
      <PageHeader title="Dashboard" description={account === undefined ? "All accounts" : accountLabel(account)}>
        <AccountFilter />
      </PageHeader>
      <ErrorNote error={overview.error} />
      <div className="grid min-w-0 grid-cols-1 gap-4">
        <BotControlCard />
        {overview.data
          ? <OverviewView o={overview.data} account={account} stale={overview.isPlaceholderData} />
          : <OverviewSkeleton />}
      </div>
    </>
  );
}
