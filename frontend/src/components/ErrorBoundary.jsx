import { Component } from 'react';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('React ErrorBoundary caught:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: 32,
          color: '#E8ECF4',
          background: '#0B1120',
          fontFamily: 'system-ui, sans-serif',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 16,
        }}>
          <h2 style={{ color: '#FF6D00', fontSize: 18 }}>Something went wrong</h2>
          <pre style={{
            color: '#8896B0',
            fontSize: 12,
            maxWidth: 600,
            overflow: 'auto',
            padding: 16,
            background: '#111B2E',
            borderRadius: 8,
            whiteSpace: 'pre-wrap',
          }}>
            {this.state.error?.message || 'Unknown error'}
          </pre>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '8px 24px',
              background: '#448AFF',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              cursor: 'pointer',
              fontSize: 14,
            }}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
