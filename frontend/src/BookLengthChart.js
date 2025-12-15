import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

const BookLengthChart = ({ data }) => {
  return (
    <ResponsiveContainer width="100%" height={300}>
  <BarChart
    data={data}
    margin={{ top: 10, right: 20, left: 0, bottom: 10 }}
    barCategoryGap="20%"
  >
    <CartesianGrid
      strokeDasharray="4 4"
      stroke="#d6d1c6"
      vertical={false}
    />

    <XAxis
      dataKey="range"
      tick={{ fill: "#6b6457", fontSize: 12 }}
      axisLine={false}
      tickLine={false}
      interval={0}
      dy={8}
    />

    <YAxis
      tick={{ fill: "#6b6457", fontSize: 12 }}
      axisLine={false}
      tickLine={false}
      width={30}
    />

    <Tooltip
      contentStyle={{
        backgroundColor: "#f3efe6",
        borderRadius: "12px",
        border: "none",
      }}
      cursor={{ fill: "rgba(0,0,0,0.04)" }}
    />

    <Bar
      dataKey="count"
      fill="#a39988"
      radius={[14, 14, 0, 0]}
      barSize={38}
    />
  </BarChart>
</ResponsiveContainer>

  );
};

export default BookLengthChart;
