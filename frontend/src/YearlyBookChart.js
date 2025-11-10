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

function YearlyBookChart({ yearlyData }) {
  if (!yearlyData || Object.keys(yearlyData).length === 0) {
    return <p>No yearly data available.</p>;
  }

  const chartData = Object.entries(yearlyData).map(([year, count]) => ({
    year,
    books: count,
  }));

  return (
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="year" />
          <YAxis allowDecimals={false} />
          <Tooltip />
          <Line
            type="monotone"
            dataKey="books"
            stroke="#a39988"
            strokeWidth={3}
            dot={{ r: 5 }}
            activeDot={{ r: 8 }}
          />
        </LineChart>
      </ResponsiveContainer>
  );
}

export default YearlyBookChart;
