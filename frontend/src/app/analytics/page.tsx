"use client";

import { useEffect, useState, useCallback, useMemo } from "react";

import { DashboardLayout } from "@/components/ui/dashboard-layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { formatCost } from "@/lib/utils";
import { useAuthGuard } from "@/hooks/useAuthGuard";
import dynamic from "next/dynamic";

// Recharts is a large dependency tree. Loading the charts on demand keeps it
// out of the initial route payload.
const RunsAreaChart = dynamic(
  () => import("@/components/charts").then((m) => m.RunsAreaChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
);
const PassRateChart = dynamic(
  () => import("@/components/charts").then((m) => m.PassRateChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
);
const RegressionChart = dynamic(
  () => import("@/components/charts").then((m) => m.RegressionChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
);
const CostChart = dynamic(
  () => import("@/components/charts").then((m) => m.CostChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
);
const SeverityChart = dynamic(
  () => import("@/components/charts").then((m) => m.SeverityChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
);
const LatencyChart = dynamic(
  () => import("@/components/charts").then((m) => m.LatencyChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
);
const CountBarChart = dynamic(
  () => import("@/components/charts").then((m) => m.CountBarChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
);
const CostAreaChart = dynamic(
  () => import("@/components/charts").then((m) => m.CostAreaChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
);
const CategoryPieChart = dynamic(
  () => import("@/components/charts").then((m) => m.CategoryPieChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
);

function ChartSkeleton() {
  return <div className="h-full w-full animate-pulse rounded-md bg-muted/40" />;
}
import { TrendingUp, Target, AlertTriangle, DollarSign, RefreshCw } from "lucide-react";

interface RunSummary {
  id: string;
  status: string;
  created_at: string;
  total_tests: number;
  passed_count: number;
  failed_count: number;
  inconclusive_count: number;
  regression_count: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  total_cost_usd: number;
  total_latency_ms: number;
}

interface AnalyticsData {
  runs_over_time: { date: string; count: number }[];
  pass_rate_over_time: { date: string; rate: number }[];
  regressions_over_time: { date: string; count: number }[];
  cost_over_time: { date: string; cost: number }[];
  latency_over_time: { date: string; latency: number }[];
  severity_distribution: { severity: string; count: number }[];
  category_distribution: { category: string; count: number }[];
  top_failing_tests: { test_case_id: string; failure_count: number }[];
}

export default function AnalyticsPage() {
  const { ready, authenticated } = useAuthGuard();
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState("7d");
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchAnalytics = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    
    try {
      const res = await api.get(`/analytics?range=${timeRange}`);
      setAnalytics(res.data);
    } catch (error) {
      console.error("Failed to fetch analytics:", error);
      setError("Failed to load analytics. Please check your connection.");      setAnalytics(null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [timeRange]);

  useEffect(() => {
    if (!ready || !authenticated) return;
    void fetchAnalytics();
  }, [ready, authenticated, fetchAnalytics]);

  useEffect(() => {
    if (!authenticated || loading) return;

    const interval = setInterval(() => {
      fetchAnalytics(true);
    }, 30000);

    return () => clearInterval(interval);
  }, [authenticated, loading, fetchAnalytics]);

  // The chart series are memoised: they were rebuilt on every render, which
  // re-created six new arrays and forced every Recharts component to
  // re-render even when the underlying data had not changed.
  const formatDay = useCallback(
    (date: string) => new Date(date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    []
  );

  const passRateData = useMemo(
    () => analytics?.pass_rate_over_time?.map(d => ({ name: formatDay(d.date), value: d.rate })) || [],
    [analytics?.pass_rate_over_time, formatDay]
  );

  const regressionData = useMemo(
    () => analytics?.regressions_over_time?.map(d => ({ name: formatDay(d.date), value: d.count })) || [],
    [analytics?.regressions_over_time, formatDay]
  );

  const costData = useMemo(
    () => analytics?.cost_over_time?.map(d => ({ name: formatDay(d.date), value: d.cost })) || [],
    [analytics?.cost_over_time, formatDay]
  );

  const runsData = useMemo(
    () => analytics?.runs_over_time?.map(d => ({ name: formatDay(d.date), value: d.count })) || [],
    [analytics?.runs_over_time, formatDay]
  );

  const severityData = useMemo(
    () =>
      analytics?.severity_distribution?.map(d => ({
        name: d.severity,
        value: d.count,
        color:
          d.severity === "critical"
            ? "#ef4444"
            : d.severity === "high"
              ? "#f97316"
              : d.severity === "medium"
                ? "#eab308"
                : "#3b82f6",
      })) || [],
    [analytics?.severity_distribution]
  );

  const categoryData = useMemo(
    () =>
      analytics?.category_distribution?.map((d, i) => ({
        name: d.category,
        value: d.count,
        color: ["#3b82f6", "#8b5cf6", "#ec4899", "#f97316", "#eab308", "#22c55e", "#06b6d4"][i % 7],
      })) || [],
    [analytics?.category_distribution]
  );

  // The period cost used to be reduced twice on every render.
  const totalCost = useMemo(
    () => (analytics?.cost_over_time ?? []).reduce((sum, d) => sum + d.cost, 0),
    [analytics?.cost_over_time]
  );

  if (!ready || !authenticated) {
    return (
      <DashboardLayout>
        <div className="flex h-[calc(100vh-4rem)] items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold">Analytics</h1>
            <p className="text-muted-foreground">Deep insights into your evaluation data</p>
            {error && (
              <p className="text-sm text-destructive mt-1 flex items-center gap-1">
                <AlertTriangle className="h-3 w-3" /> {error}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <Button 
              variant="outline" 
              size="icon"
              onClick={() => fetchAnalytics(true)}
              disabled={refreshing}
              title="Refresh analytics"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            </Button>
            <Select value={timeRange} onValueChange={setTimeRange}>
              <SelectTrigger className="w-48"><SelectValue placeholder="Time range" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="7d">Last 7 days</SelectItem>
                <SelectItem value="30d">Last 30 days</SelectItem>
                <SelectItem value="90d">Last 90 days</SelectItem>
                <SelectItem value="1y">Last year</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Runs</CardTitle>
              <Target className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{analytics?.runs_over_time?.reduce((sum, d) => sum + d.count, 0) || 0}</div>
              <p className="text-xs text-muted-foreground">{timeRange} period</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Avg Pass Rate</CardTitle>
              <TrendingUp className="h-4 w-4 text-green-600" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-600">
                {analytics?.pass_rate_over_time?.length
                  ? (analytics.pass_rate_over_time.reduce((sum, d) => sum + d.rate, 0) / analytics.pass_rate_over_time.length).toFixed(1) + "%"
                  : "N/A"}
              </div>
              <p className="text-xs text-muted-foreground">Average over period</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Regressions</CardTitle>
              <AlertTriangle className="h-4 w-4 text-destructive" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-destructive">
                {analytics?.regressions_over_time?.reduce((sum, d) => sum + d.count, 0) || 0}
              </div>
              <p className="text-xs text-muted-foreground">{timeRange} period</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Cost</CardTitle>
              <DollarSign className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {totalCost > 0 ? formatCost(totalCost) : "N/A"}
              </div>
              <p className="text-xs text-muted-foreground">{timeRange} period</p>
            </CardContent>
          </Card>
        </div>

        <Tabs defaultValue="overview" className="space-y-4">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="performance">Performance</TabsTrigger>
            <TabsTrigger value="quality">Quality</TabsTrigger>
            <TabsTrigger value="cost">Cost</TabsTrigger>
          </TabsList>

          <TabsContent value="overview">
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader><CardTitle>Runs Over Time</CardTitle></CardHeader>
                <CardContent>
                  <div className="h-80">
                    <RunsAreaChart data={runsData} />
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle>Pass Rate Trend</CardTitle></CardHeader>
                <CardContent>
                  <div className="h-80">
                    <PassRateChart data={passRateData} />
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle>Regression Trend</CardTitle></CardHeader>
                <CardContent>
                  <div className="h-80">
                    <RegressionChart data={regressionData} />
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle>Cost Trend</CardTitle></CardHeader>
                <CardContent>
                  <div className="h-80">
                    <CostChart data={costData} />
                  </div>
                </CardContent>
              </Card>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader><CardTitle>Severity Distribution</CardTitle></CardHeader>
                <CardContent>
                  <div className="h-64">
                    <SeverityChart data={severityData.length > 0 ? severityData : [{ name: "None", value: 1, color: "hsl(var(--muted))" }]} />
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle>Category Distribution</CardTitle></CardHeader>
                <CardContent>
                  <div className="h-64">
                    <CategoryPieChart data={categoryData.length > 0 ? categoryData : [{ name: "None", value: 1, color: "hsl(var(--muted))" }]} />
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="performance">
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader><CardTitle>Latency Over Time</CardTitle></CardHeader>
                <CardContent>
                  <div className="h-80">
                    <LatencyChart data={analytics?.latency_over_time?.map(d => ({
                      name: new Date(d.date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
                      value: d.latency,
                    })) || []} />
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle>Tests per Run</CardTitle></CardHeader>
                <CardContent>
                  <div className="h-80">
                    <CountBarChart data={runsData} />
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="quality">
            <Card>
              <CardHeader><CardTitle>Top Failing Tests</CardTitle></CardHeader>
              <CardContent>
                {(analytics?.top_failing_tests?.length ?? 0) > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left p-4">Test Case</th>
                          <th className="text-left p-4">Failure Count</th>
                        </tr>
                      </thead>
                      <tbody>
                        {analytics?.top_failing_tests?.map((test) => (
                          <tr key={test.test_case_id} className="border-b">
                            <td className="p-4 font-mono text-sm">{test.test_case_id}</td>
                            <td className="p-4"><span className="bg-destructive/10 text-destructive px-2 py-1 rounded">{test.failure_count}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-center py-8 text-muted-foreground">No failing tests data available</p>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="cost">
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader><CardTitle>Daily Cost Breakdown</CardTitle></CardHeader>
                <CardContent>
                  <div className="h-80">
                    <CountBarChart
                      data={costData.length > 0 ? costData : [{ name: "Day 1", value: 0 }]}
                      fill="hsl(var(--secondary-foreground))"
                    />
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle>Cumulative Cost</CardTitle></CardHeader>
                <CardContent>
                  <div className="h-80">
                    <CostAreaChart
                      data={analytics?.cost_over_time?.map((d, i, arr) => ({
                        name: new Date(d.date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
                        value: arr.slice(0, i + 1).reduce((sum, item) => sum + item.cost, 0),
                      })) || [{ name: "Day 1", value: 0 }]}
                    />
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
}

