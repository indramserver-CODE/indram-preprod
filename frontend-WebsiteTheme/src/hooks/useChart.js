import { useEffect, useRef } from 'react';
import { Chart } from 'chart.js/auto';

Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = '#4a5568';
Chart.defaults.borderColor = 'rgba(0, 0, 0, 0.07)';
Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(26, 32, 44, 0.95)';
Chart.defaults.plugins.tooltip.borderColor = 'rgba(255, 255, 255, 0.1)';
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.titleColor = '#f2f2f2';
Chart.defaults.plugins.tooltip.bodyColor = '#d1d1d6';
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.legend.labels.color = '#4a5568';

export const CHART_COLORS = {
  BLUE: '#6366f1',
  GREEN: '#15803d',
  RED: '#e53e3e',
  AMBER: '#f6ad55',
  PURPLE: '#9f7aea',
  TEAL: '#38b2ac',
};
export const PALETTE = [
  '#00cc35',
  CHART_COLORS.BLUE,
  CHART_COLORS.TEAL,
  CHART_COLORS.PURPLE,
  CHART_COLORS.AMBER,
  CHART_COLORS.RED,
  '#f687b3',
  '#68d391',
  '#63b3ed',
  '#fbb6ce',
];

export function hexAlpha(hex, a) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${a})`;
}

/**
 * Returns a canvas ref. Pass a `build` function that receives the canvas
 * context and returns a Chart config; it's called whenever `data` changes.
 * The chart is destroyed and recreated on each data change, and destroyed on unmount.
 */
export function useChart(config) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!config || !canvasRef.current) return;
    if (chartRef.current) {
      chartRef.current.destroy();
      chartRef.current = null;
    }
    const ctx = canvasRef.current.getContext('2d');
    chartRef.current = new Chart(ctx, config);
    return () => {
      if (chartRef.current) {
        chartRef.current.destroy();
        chartRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  return canvasRef;
}
