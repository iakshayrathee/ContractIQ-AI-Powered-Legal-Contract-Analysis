"use client";

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

interface TrendData {
  date: string;
  score: number;
}

interface Props {
  data: TrendData[];
  height?: number;
}

export default function RiskTrendChart({ data, height = 120 }: Props) {
  if (!data || data.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ left: -20, right: 0, top: 5, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fill: "#6B6F8A", fontSize: 10 }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          domain={[0, 100]}
          tick={{ fill: "#6B6F8A", fontSize: 10 }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "rgba(15, 18, 32, 0.95)",
            border: "1px solid rgba(201, 168, 76, 0.2)",
            borderRadius: "8px",
          }}
          labelStyle={{ color: "#fff" }}
          formatter={(value: string | number | readonly (string | number)[] | undefined) => value !== undefined ? [`${value}`, "Risk Score"] : ["", ""]}
        />
        <Line
          type="monotone"
          dataKey="score"
          stroke="#C9A84C"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
