import { Suspense, lazy, Component } from 'react';
import './CenterViewport.css';

const Scene3D = lazy(() => import('./Scene3D'));

class ViewportErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('3D Viewport error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="viewport-fallback">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" strokeWidth="1.5">
            <circle cx="12" cy="12" r="10" />
            <ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(-30 12 12)" />
            <ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(30 12 12)" />
          </svg>
          <div className="viewport-fallback-title">3D View Unavailable</div>
          <div className="viewport-fallback-text">
            {this.state.error?.message || 'WebGL failed to initialize'}
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function CenterViewport() {
  return (
    <div className="center-viewport">
      <ViewportErrorBoundary>
        <Suspense
          fallback={
            <div className="viewport-fallback">
              <div className="viewport-spinner" />
              <div className="viewport-fallback-text">Loading 3D viewport...</div>
            </div>
          }
        >
          <Scene3D />
        </Suspense>
      </ViewportErrorBoundary>
    </div>
  );
}
