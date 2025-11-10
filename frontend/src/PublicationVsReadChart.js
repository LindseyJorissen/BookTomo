import React from "react";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

function PublicationVsReadChart({ data, type }) {
  if (!data || data.length === 0) return <p>No data available.</p>;

  const xLabel = type === "month" ? "Month Read" : "Year Read";

  return (
    <ResponsiveContainer width="100%" height={400}>
      <ScatterChart margin={{ top: 20, right: 30, bottom: 40, left: 40 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          type="number"
          dataKey="read_value"
          name={xLabel}
          label={{ value: xLabel, position: "bottom", offset: 0 }}
          domain={["dataMin", "dataMax"]}
          tickFormatter={(value) =>
            type === "month"
              ? new Date(0, value - 1).toLocaleString("default", { month: "short" })
              : value
          }
        />
        <YAxis
          type="number"
          dataKey="pub_year"
          name="Publication Year"
          label={{ value: "Publication Year", angle: -90, position: "insideLeft" }}
          domain={["dataMin", "dataMax"]}
        />
        <Tooltip
          cursor={{ strokeDasharray: "3 3" }}
          formatter={(value, name) =>
            name === "pub_year" ? `Publication: ${value}` : `Read: ${value}`
          }
        />
        <Scatter data={data} fill="#a39988" />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

export default PublicationVsReadChart;
