import { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import { getConjunctionHistory } from '../../api/client';

export default function ConjunctionHistoryChart({ eventId }) {
  const svgRef = useRef(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!eventId) return;
    setLoading(true);
    getConjunctionHistory(eventId)
      .then((res) => {
        setData(res.data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [eventId]);

  useEffect(() => {
    if (!data || data.length < 2 || !svgRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const margin = { top: 8, right: 8, bottom: 24, left: 54 };
    const width = 280 - margin.left - margin.right;
    const height = 120 - margin.top - margin.bottom;

    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    const points = data
      .filter((d) => d.screened_at && d.collision_probability > 0)
      .map((d) => ({
        date: new Date(d.screened_at),
        pc: d.collision_probability,
        miss: d.miss_distance_m,
      }));

    if (points.length < 2) return;

    const x = d3
      .scaleTime()
      .domain(d3.extent(points, (d) => d.date))
      .range([0, width]);

    const pcMin = d3.min(points, (d) => d.pc);
    const pcMax = d3.max(points, (d) => d.pc);
    const y = d3
      .scaleLog()
      .domain([Math.max(1e-15, pcMin * 0.5), pcMax * 2])
      .range([height, 0])
      .clamp(true);

    // Axes
    g.append('g')
      .attr('transform', `translate(0,${height})`)
      .call(d3.axisBottom(x).ticks(3).tickFormat(d3.timeFormat('%m/%d')))
      .selectAll('text')
      .style('fill', 'var(--text-tertiary)')
      .style('font-size', '9px');

    g.append('g')
      .call(d3.axisLeft(y).ticks(3, '.0e'))
      .selectAll('text')
      .style('fill', 'var(--text-tertiary)')
      .style('font-size', '9px');

    // Style axis lines
    g.selectAll('.domain, .tick line')
      .style('stroke', 'var(--border-primary)');

    // Line
    const line = d3
      .line()
      .x((d) => x(d.date))
      .y((d) => y(d.pc));

    g.append('path')
      .datum(points)
      .attr('fill', 'none')
      .attr('stroke', 'var(--accent-primary)')
      .attr('stroke-width', 1.5)
      .attr('d', line);

    // Dots
    g.selectAll('circle')
      .data(points)
      .enter()
      .append('circle')
      .attr('cx', (d) => x(d.date))
      .attr('cy', (d) => y(d.pc))
      .attr('r', 3)
      .attr('fill', 'var(--accent-primary)');
  }, [data]);

  if (loading) return null;
  if (!data || data.length < 2) return null;

  return (
    <div className="conjunction-history-chart">
      <div className="section-title">SCREENING HISTORY</div>
      <svg ref={svgRef} width={280} height={120} />
    </div>
  );
}
