import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
} from "recharts";

function YearlyBookChart({ yearlyData, type }) {
  if (!yearlyData || Object.keys(yearlyData).length === 0) {
    return <p>No data available.</p>;
  }

  // Convert data object {2020: 12, 2021: 7, ...} or {1: 4, 2: 3, ...} to array
  const chartData = Object.entries(yearlyData).map(([key, value]) => ({
    label:
      type === "month"
        ? new Date(0, key - 1).toLocaleString("default", { month: "short" })
        : key,
    books: value,
  }));

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="label" />
        <YAxis allowDecimals={false} />
        <Tooltip />
        <Line
          type="monotone"
          dataKey="books"
          stroke="#a39988"
          strokeWidth={3}
          dot={{ r: 5 }}
          activeDot={{ r: 8 }}
          isAnimationActive={true}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export default YearlyBookChart;
