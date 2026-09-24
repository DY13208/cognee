from pathlib import Path

path = Path(r"d:\cognee\cognee-frontend\src\app\(app)\teleology\TeleologyPage.tsx")
text = path.read_text(encoding="utf-8")

start = text.find("  const refresh = useCallback(async () => {")
end2 = text.find("  const annotations = useMemo(")
if start < 0 or end2 < 0:
    raise SystemExit(f"markers {start} {end2}")

new = r'''  const [goalQuery, setGoalQuery] = useState("");
  const [goalHits, setGoalHits] = useState<GraphNodeSummary[]>([]);
  const [goalMenuOpen, setGoalMenuOpen] = useState(false);
  const [goalSearching, setGoalSearching] = useState(false);
  const [goalsTotal, setGoalsTotal] = useState<number | null>(null);
  const [selectedGoal, setSelectedGoal] = useState<GraphNodeSummary | null>(null);
  const goalSearchSeq = useRef(0);

  const refresh = useCallback(async () => {
    if (!cogniInstance || !datasetId) {
      setGraph(null);
      setBrainNodes([]);
      setTreeAdvances([]);
      setGoalHits([]);
      setSelectedGoal(null);
      setGoalsTotal(null);
      setLoading(false);
      return;
    }
    setLoadError(null);
    try {
      // Light first paint: status + goal count. Graph loads after a purpose is chosen.
      const [yaml, sample] = await Promise.all([
        getTeleology(cogniInstance).catch(() => null),
        getGraphAnnotations(cogniInstance, datasetId, {
          limit: 1,
          goalsLimit: 0,
        }),
      ]);
      if (yaml) setStatus(yaml);
      setBrainNodes([]);
      setTreeAdvances([]);
      setGoalsTotal(sample.goals_total ?? sample.goals?.length ?? null);
      if (lensGoalId) {
        const neighbourhood = await getGraphAnnotations(cogniInstance, datasetId, {
          limit: 80,
          goalsLimit: 40,
          goalId: lensGoalId,
        });
        setGraph(neighbourhood);
      } else {
        setGraph({
          ...sample,
          goals: [],
          annotations: [],
          nodes: [],
        });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setLoadError(msg);
      setGraph(null);
    } finally {
      setLoading(false);
    }
  }, [cogniInstance, datasetId, lensGoalId]);

  const searchGoals = useCallback(
    async (query: string) => {
      if (!cogniInstance || !datasetId) return;
      const seq = ++goalSearchSeq.current;
      setGoalSearching(true);
      try {
        const res = await getGraphAnnotations(cogniInstance, datasetId, {
          q: query.trim() || undefined,
          limit: 1,
          goalsLimit: 40,
        });
        if (seq !== goalSearchSeq.current) return;
        setGoalsTotal(res.goals_total ?? res.goals.length);
        setGoalHits(
          (res.goals || []).map((g) => ({
            ...g,
            name: displayName(g.name, g.id),
            description: displayName(g.description || ""),
          })),
        );
      } catch {
        if (seq !== goalSearchSeq.current) return;
        setGoalHits([]);
      } finally {
        if (seq === goalSearchSeq.current) setGoalSearching(false);
      }
    },
    [cogniInstance, datasetId],
  );

  useEffect(() => {
    if (!cogniInstance || isInitializing || datasetsLoading) return;
    if (!selectedDataset && datasets[0]) setSelectedDataset(datasets[0]);
  }, [cogniInstance, isInitializing, datasetsLoading, datasets, selectedDataset, setSelectedDataset]);

  useEffect(() => {
    if (!cogniInstance || isInitializing || !datasetId) return;
    setLoading(true);
    setLensGoalId("");
    setSelectedGoal(null);
    setGoalQuery("");
    setGoalHits([]);
    refresh();
  }, [cogniInstance, isInitializing, datasetId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!cogniInstance || !datasetId || isInitializing) return;
    if (!lensGoalId) {
      setGraph((prev) => (prev ? { ...prev, goals: [], annotations: [], nodes: [] } : prev));
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const neighbourhood = await getGraphAnnotations(cogniInstance, datasetId, {
          limit: 80,
          goalsLimit: 40,
          goalId: lensGoalId,
        });
        if (!cancelled) setGraph(neighbourhood);
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [cogniInstance, datasetId, lensGoalId, isInitializing]);

  useEffect(() => {
    if (!goalMenuOpen || !cogniInstance || !datasetId) return;
    const handle = window.setTimeout(() => {
      void searchGoals(goalQuery);
    }, 280);
    return () => window.clearTimeout(handle);
  }, [goalQuery, goalMenuOpen, cogniInstance, datasetId, searchGoals]);

  const goalOptions = useMemo((): GraphNodeSummary[] => {
    const byId = new Map<string, GraphNodeSummary>();
    for (const g of goalHits) byId.set(g.id, g);
    if (selectedGoal) byId.set(selectedGoal.id, selectedGoal);
    return Array.from(byId.values());
  }, [goalHits, selectedGoal]);

  function pickGoal(goal: GraphNodeSummary | null) {
    if (!goal) {
      setLensGoalId("");
      setSelectedGoal(null);
      setGoalQuery("");
      setGoalMenuOpen(false);
      return;
    }
    const cleaned = {
      ...goal,
      name: displayName(goal.name, goal.id),
      description: displayName(goal.description || ""),
    };
    setSelectedGoal(cleaned);
    setLensGoalId(cleaned.id);
    setGoalQuery(cleaned.cpd_kind === "goal" ? `CPD · ${cleaned.name}` : cleaned.name);
    setGoalMenuOpen(false);
  }

'''

path.write_text(text[:start] + new + text[end2:], encoding="utf-8")
print("ok", start, end2)
