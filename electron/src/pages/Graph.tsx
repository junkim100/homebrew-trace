import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import type {
  GraphNode,
  GraphEdge,
  EntityTypeCount,
  EntityDetailsResponse,
} from '../types/trace-api';

// Colors for entity types
const TYPE_COLORS: Record<string, string> = {
  topic: '#00d4ff',
  app: '#34c759',
  domain: '#ff9500',
  document: '#af52de',
  artist: '#ff2d55',
  track: '#5856d6',
  video: '#ff3b30',
  game: '#ffcc00',
  person: '#007aff',
  project: '#32d74b',
  default: '#8e8e93',
};

// Simple force simulation
interface SimNode extends GraphNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

export function Graph() {
  const navigate = useNavigate();
  const svgRef = useRef<SVGSVGElement>(null);

  const [nodes, setNodes] = useState<SimNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [entityTypes, setEntityTypes] = useState<EntityTypeCount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const [entityDetails, setEntityDetails] = useState<EntityDetailsResponse | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);

  const [daysBack, setDaysBack] = useState(30);
  const [nodeLimit, setNodeLimit] = useState(50);
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set());

  const [viewBox, setViewBox] = useState({ x: 0, y: 0, width: 800, height: 600 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });

  // Load graph data
  const loadGraph = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const result = await window.traceAPI.graph.getData({
        daysBack,
        entityTypes: selectedTypes.size > 0 ? Array.from(selectedTypes) : undefined,
        limit: nodeLimit,
      });

      if (result.success) {
        // Initialize node positions randomly
        const width = 800;
        const height = 600;
        const simNodes: SimNode[] = result.nodes.map((node) => ({
          ...node,
          x: Math.random() * width,
          y: Math.random() * height,
          vx: 0,
          vy: 0,
        }));

        setNodes(simNodes);
        setEdges(result.edges);

        // Run simple force simulation
        runSimulation(simNodes, result.edges);
      } else {
        setError(result.error || 'Failed to load graph');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load graph');
    } finally {
      setLoading(false);
    }
  }, [daysBack, nodeLimit, selectedTypes]);

  // Load entity types
  useEffect(() => {
    window.traceAPI.graph.getEntityTypes().then((result) => {
      if (result.success) {
        setEntityTypes(result.types);
      }
    });
  }, []);

  // Load graph when parameters change
  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  // Simple force-directed simulation
  const runSimulation = (simNodes: SimNode[], simEdges: GraphEdge[]) => {
    const iterations = 100;
    const width = 800;
    const height = 600;

    // Build adjacency lookup
    const nodeMap = new Map(simNodes.map((n) => [n.id, n]));

    for (let i = 0; i < iterations; i++) {
      // Apply repulsion between all nodes
      for (let j = 0; j < simNodes.length; j++) {
        for (let k = j + 1; k < simNodes.length; k++) {
          const nodeA = simNodes[j];
          const nodeB = simNodes[k];

          const dx = nodeB.x - nodeA.x;
          const dy = nodeB.y - nodeA.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 5000 / (dist * dist);

          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;

          nodeA.vx -= fx;
          nodeA.vy -= fy;
          nodeB.vx += fx;
          nodeB.vy += fy;
        }
      }

      // Apply attraction along edges
      for (const edge of simEdges) {
        const source = nodeMap.get(edge.source);
        const target = nodeMap.get(edge.target);

        if (source && target) {
          const dx = target.x - source.x;
          const dy = target.y - source.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = dist * 0.01 * edge.weight;

          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;

          source.vx += fx;
          source.vy += fy;
          target.vx -= fx;
          target.vy -= fy;
        }
      }

      // Apply center gravity
      for (const node of simNodes) {
        node.vx += (width / 2 - node.x) * 0.001;
        node.vy += (height / 2 - node.y) * 0.001;
      }

      // Update positions with damping
      const damping = 0.9;
      for (const node of simNodes) {
        node.vx *= damping;
        node.vy *= damping;
        node.x += node.vx;
        node.y += node.vy;

        // Keep in bounds
        node.x = Math.max(50, Math.min(width - 50, node.x));
        node.y = Math.max(50, Math.min(height - 50, node.y));
      }
    }

    setNodes([...simNodes]);
  };

  // Handle entity selection
  const handleNodeClick = async (nodeId: string) => {
    setSelectedEntity(nodeId);
    setDetailsLoading(true);

    try {
      const result = await window.traceAPI.graph.getEntityDetails(nodeId);
      setEntityDetails(result);
    } catch (err) {
      console.error('Failed to load entity details:', err);
      setEntityDetails(null);
    } finally {
      setDetailsLoading(false);
    }
  };

  // Pan handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button === 0 && e.target === svgRef.current) {
      setIsPanning(true);
      setPanStart({ x: e.clientX, y: e.clientY });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isPanning) {
      const dx = e.clientX - panStart.x;
      const dy = e.clientY - panStart.y;
      setViewBox((prev) => ({
        ...prev,
        x: prev.x - dx,
        y: prev.y - dy,
      }));
      setPanStart({ x: e.clientX, y: e.clientY });
    }
  };

  const handleMouseUp = () => {
    setIsPanning(false);
  };

  // Zoom handler
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const scale = e.deltaY > 0 ? 1.1 : 0.9;

    setViewBox((prev) => {
      const newWidth = prev.width * scale;
      const newHeight = prev.height * scale;
      const dx = (newWidth - prev.width) / 2;
      const dy = (newHeight - prev.height) / 2;

      return {
        x: prev.x - dx,
        y: prev.y - dy,
        width: newWidth,
        height: newHeight,
      };
    });
  };

  // Toggle type filter
  const toggleType = (type: string) => {
    setSelectedTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  };

  // Build node lookup for edge rendering
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  return (
    <div style={styles.container}>
      <div className="titlebar" style={styles.titlebar}>
        <button onClick={() => navigate(-1)} style={styles.backButton}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5" />
            <path d="M12 19l-7-7 7-7" />
          </svg>
          Back
        </button>
        <h1 style={styles.title}>Knowledge Graph</h1>
        <div style={styles.titlebarSpacer} />
      </div>

      <div style={styles.main}>
        <div style={styles.sidebar}>
          <div style={styles.filterSection}>
            <h3 style={styles.sectionTitle}>Time Range</h3>
            <select
              value={daysBack}
              onChange={(e) => setDaysBack(parseInt(e.target.value))}
              style={styles.select}
            >
              <option value={7}>Last 7 days</option>
              <option value={14}>Last 14 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </select>
          </div>

          <div style={styles.filterSection}>
            <h3 style={styles.sectionTitle}>Node Limit</h3>
            <select
              value={nodeLimit}
              onChange={(e) => setNodeLimit(parseInt(e.target.value))}
              style={styles.select}
            >
              <option value={25}>25 nodes</option>
              <option value={50}>50 nodes</option>
              <option value={100}>100 nodes</option>
              <option value={200}>200 nodes</option>
            </select>
          </div>

          <div style={styles.filterSection}>
            <h3 style={styles.sectionTitle}>Entity Types</h3>
            <div style={styles.typeFilters}>
              {entityTypes.map((t) => (
                <button
                  key={t.type}
                  onClick={() => toggleType(t.type)}
                  style={{
                    ...styles.typeButton,
                    backgroundColor: selectedTypes.has(t.type) || selectedTypes.size === 0
                      ? TYPE_COLORS[t.type] || TYPE_COLORS.default
                      : 'transparent',
                    color: selectedTypes.has(t.type) || selectedTypes.size === 0
                      ? 'white'
                      : TYPE_COLORS[t.type] || TYPE_COLORS.default,
                    borderColor: TYPE_COLORS[t.type] || TYPE_COLORS.default,
                  }}
                >
                  {t.type} ({t.count})
                </button>
              ))}
            </div>
          </div>

          <div style={styles.statsSection}>
            <div style={styles.stat}>
              <span style={styles.statLabel}>Nodes</span>
              <span style={styles.statValue}>{nodes.length}</span>
            </div>
            <div style={styles.stat}>
              <span style={styles.statLabel}>Edges</span>
              <span style={styles.statValue}>{edges.length}</span>
            </div>
          </div>

          {/* Entity details panel */}
          {selectedEntity && (
            <div style={styles.detailsPanel}>
              <div style={styles.detailsHeader}>
                <h3 style={styles.sectionTitle}>Entity Details</h3>
                <button
                  onClick={() => setSelectedEntity(null)}
                  style={styles.closeButton}
                >
                  ×
                </button>
              </div>

              {detailsLoading ? (
                <div style={styles.detailsLoading}>Loading...</div>
              ) : entityDetails?.entity ? (
                <>
                  <div style={styles.entityName}>{entityDetails.entity.name}</div>
                  <div
                    style={{
                      ...styles.entityType,
                      color: TYPE_COLORS[entityDetails.entity.type] || TYPE_COLORS.default,
                    }}
                  >
                    {entityDetails.entity.type}
                  </div>

                  {entityDetails.related && entityDetails.related.length > 0 && (
                    <div style={styles.relatedSection}>
                      <h4 style={styles.subsectionTitle}>Related ({entityDetails.related.length})</h4>
                      <div style={styles.relatedList}>
                        {entityDetails.related.slice(0, 5).map((r) => (
                          <div
                            key={r.id}
                            style={styles.relatedItem}
                            onClick={() => handleNodeClick(r.id)}
                          >
                            <span style={styles.relatedName}>{r.name}</span>
                            <span style={styles.relatedEdge}>{r.edgeType}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {entityDetails.notes && entityDetails.notes.length > 0 && (
                    <div style={styles.notesSection}>
                      <h4 style={styles.subsectionTitle}>Notes ({entityDetails.notes.length})</h4>
                      <div style={styles.notesList}>
                        {entityDetails.notes.slice(0, 3).map((n) => (
                          <div key={n.noteId} style={styles.noteItem}>
                            <span style={styles.noteDate}>
                              {new Date(n.timestamp).toLocaleDateString()}
                            </span>
                            <span style={styles.noteSummary}>
                              {n.summary.slice(0, 80)}...
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div style={styles.detailsError}>Entity not found</div>
              )}
            </div>
          )}
        </div>

        <div style={styles.graphArea}>
          {loading ? (
            <div style={styles.loadingOverlay}>Loading graph...</div>
          ) : error ? (
            <div style={styles.errorOverlay}>{error}</div>
          ) : nodes.length === 0 ? (
            <div style={styles.emptyOverlay}>
              No entities found for the selected filters.
            </div>
          ) : (
            <svg
              ref={svgRef}
              style={styles.svg}
              viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
              onWheel={handleWheel}
            >
              {/* Edges */}
              <g>
                {edges.map((edge, idx) => {
                  const source = nodeMap.get(edge.source);
                  const target = nodeMap.get(edge.target);
                  if (!source || !target) return null;

                  return (
                    <line
                      key={idx}
                      x1={source.x}
                      y1={source.y}
                      x2={target.x}
                      y2={target.y}
                      stroke="var(--border)"
                      strokeWidth={Math.max(1, edge.weight * 3)}
                      strokeOpacity={0.5}
                    />
                  );
                })}
              </g>

              {/* Nodes */}
              <g>
                {nodes.map((node) => {
                  const isSelected = selectedEntity === node.id;
                  const radius = Math.max(8, Math.min(20, 6 + node.edgeCount));

                  return (
                    <g
                      key={node.id}
                      style={{ cursor: 'pointer' }}
                      onClick={() => handleNodeClick(node.id)}
                    >
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={radius}
                        fill={TYPE_COLORS[node.type] || TYPE_COLORS.default}
                        stroke={isSelected ? 'white' : 'none'}
                        strokeWidth={isSelected ? 3 : 0}
                        opacity={0.9}
                      />
                      <text
                        x={node.x}
                        y={node.y + radius + 12}
                        textAnchor="middle"
                        fill="var(--text-secondary)"
                        fontSize="10"
                        style={{ pointerEvents: 'none' }}
                      >
                        {node.label.length > 15 ? node.label.slice(0, 15) + '...' : node.label}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>
          )}

          <div style={styles.instructions}>
            Scroll to zoom, drag to pan, click nodes for details
          </div>
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
  },
  titlebar: {
    display: 'flex',
    alignItems: 'center',
    padding: '0 1rem',
    gap: '1rem',
  },
  backButton: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    backgroundColor: 'transparent',
    border: 'none',
    color: 'var(--accent)',
    fontSize: '0.9rem',
    cursor: 'pointer',
    padding: '0.5rem',
    borderRadius: '6px',
  },
  title: {
    fontSize: '1.25rem',
    fontWeight: 600,
    color: 'var(--text-primary)',
    margin: 0,
  },
  titlebarSpacer: {
    flex: 1,
  },
  main: {
    flex: 1,
    display: 'flex',
    overflow: 'hidden',
  },
  sidebar: {
    width: '280px',
    borderRight: '1px solid var(--border)',
    padding: '1rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
    overflow: 'auto',
  },
  filterSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  sectionTitle: {
    fontSize: '0.75rem',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    margin: 0,
  },
  select: {
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '6px',
    padding: '0.5rem',
    fontSize: '0.85rem',
    color: 'var(--text-primary)',
    cursor: 'pointer',
  },
  typeFilters: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '0.375rem',
  },
  typeButton: {
    padding: '0.25rem 0.5rem',
    fontSize: '0.75rem',
    borderRadius: '4px',
    border: '1px solid',
    cursor: 'pointer',
    transition: 'all 0.15s',
  },
  statsSection: {
    display: 'flex',
    gap: '1rem',
    padding: '0.75rem',
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: '8px',
  },
  stat: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
  },
  statLabel: {
    fontSize: '0.7rem',
    color: 'var(--text-tertiary)',
    textTransform: 'uppercase',
  },
  statValue: {
    fontSize: '1.25rem',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  detailsPanel: {
    flex: 1,
    minHeight: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
    padding: '0.75rem',
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: '8px',
    overflow: 'auto',
  },
  detailsHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  closeButton: {
    backgroundColor: 'transparent',
    border: 'none',
    color: 'var(--text-secondary)',
    fontSize: '1.5rem',
    cursor: 'pointer',
    padding: '0',
    lineHeight: 1,
  },
  detailsLoading: {
    color: 'var(--text-secondary)',
    fontSize: '0.85rem',
  },
  detailsError: {
    color: '#ff3b30',
    fontSize: '0.85rem',
  },
  entityName: {
    fontSize: '1rem',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  entityType: {
    fontSize: '0.75rem',
    fontWeight: 500,
    textTransform: 'uppercase',
  },
  relatedSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.375rem',
  },
  subsectionTitle: {
    fontSize: '0.7rem',
    fontWeight: 600,
    color: 'var(--text-tertiary)',
    textTransform: 'uppercase',
    margin: 0,
  },
  relatedList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
  },
  relatedItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '0.25rem 0.375rem',
    backgroundColor: 'var(--bg-tertiary)',
    borderRadius: '4px',
    cursor: 'pointer',
  },
  relatedName: {
    fontSize: '0.8rem',
    color: 'var(--text-primary)',
  },
  relatedEdge: {
    fontSize: '0.7rem',
    color: 'var(--text-tertiary)',
  },
  notesSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.375rem',
  },
  notesList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
  },
  noteItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.125rem',
    padding: '0.375rem',
    backgroundColor: 'var(--bg-tertiary)',
    borderRadius: '4px',
  },
  noteDate: {
    fontSize: '0.7rem',
    color: 'var(--text-tertiary)',
  },
  noteSummary: {
    fontSize: '0.8rem',
    color: 'var(--text-secondary)',
    lineHeight: 1.3,
  },
  graphArea: {
    flex: 1,
    position: 'relative',
    overflow: 'hidden',
    backgroundColor: 'var(--bg-primary)',
  },
  svg: {
    width: '100%',
    height: '100%',
    cursor: 'grab',
  },
  loadingOverlay: {
    position: 'absolute',
    inset: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: 'var(--text-secondary)',
    fontSize: '1rem',
  },
  errorOverlay: {
    position: 'absolute',
    inset: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#ff3b30',
    fontSize: '1rem',
  },
  emptyOverlay: {
    position: 'absolute',
    inset: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: 'var(--text-secondary)',
    fontSize: '1rem',
  },
  instructions: {
    position: 'absolute',
    bottom: '1rem',
    left: '50%',
    transform: 'translateX(-50%)',
    padding: '0.5rem 1rem',
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: '6px',
    fontSize: '0.8rem',
    color: 'var(--text-tertiary)',
  },
};

export default Graph;
