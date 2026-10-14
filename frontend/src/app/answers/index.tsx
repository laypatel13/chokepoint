// The card under each answer, chosen by the tool that answered.
import type { BlastRadius, Chokepoints, ExplainPath, GraphStats, Incident, Investigate, KnownAdvisories, LockfileSaved, NightjarReplay, Recall, SafeVersion, ToolResult } from "../../lib/types";
import { BlastRadiusCard } from "./BlastRadius";
import { ChokepointsCard } from "./Chokepoints";
import { ExplainPathCard } from "./ExplainPath";
import { GraphStatsCard } from "./GraphStats";
import { IncidentCard } from "./Incident";
import { InvestigateCard } from "./Investigate";
import { KnownAdvisoriesCard } from "./KnownAdvisories";
import { LockfileSavedCard } from "./LockfileSaved";
import { NightjarLogCard } from "./NightjarLog";
import { RecallCard } from "./Recall";
import { SafeVersionCard } from "./SafeVersion";

export function AnswerCard({ tool, result, asOf }: { tool: string; result: ToolResult; asOf?: string | null }) {
  switch (tool) {
    case "explain_path": return <ExplainPathCard r={result as ExplainPath} asOf={asOf} />;
    case "chokepoints": return <ChokepointsCard r={result as Chokepoints} />;
    case "lockfile_saved_you": return <LockfileSavedCard r={result as LockfileSaved} />;
    case "safe_version": return <SafeVersionCard r={result as SafeVersion} />;
    case "blast_radius": return <BlastRadiusCard r={result as BlastRadius} />;
    case "known_advisories": return <KnownAdvisoriesCard r={result as KnownAdvisories} />;
    case "incident": return <IncidentCard r={result as Incident} />;
    case "graph_stats": return <GraphStatsCard r={result as GraphStats} />;
    case "investigate": return <InvestigateCard r={result as Investigate} />;
    case "recall": return <RecallCard r={result as Recall} />;
    case "nightjar": return <NightjarLogCard r={result as NightjarReplay} />;
    default: return null;
  }
}
