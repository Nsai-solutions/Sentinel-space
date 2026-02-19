import { useEffect } from 'react';
import TopBar from './components/layout/TopBar';
import LeftPanel from './components/layout/LeftPanel';
import CenterViewport from './components/layout/CenterViewport';
import RightPanel from './components/layout/RightPanel';
import BottomPanel from './components/layout/BottomPanel';
import useAssetStore from './stores/assetStore';
import useConjunctionStore from './stores/conjunctionStore';
import useAlertStore from './stores/alertStore';
import useUIStore from './stores/uiStore';
import './App.css';

function App() {
  const loadAssets = useAssetStore((s) => s.loadAssets);
  const loadConjunctions = useConjunctionStore((s) => s.loadConjunctions);
  const loadSummary = useConjunctionStore((s) => s.loadSummary);
  const loadUnreadCount = useAlertStore((s) => s.loadUnreadCount);
  const bottomPanelExpanded = useUIStore((s) => s.bottomPanelExpanded);

  useEffect(() => {
    loadAssets();
    loadConjunctions();
    loadSummary();
    loadUnreadCount();

    // Refresh periodically
    const interval = setInterval(() => {
      loadSummary();
      loadUnreadCount();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="app-layout">
      <TopBar />
      <div className="app-main">
        <LeftPanel />
        <CenterViewport />
        <RightPanel />
      </div>
      <BottomPanel expanded={bottomPanelExpanded} />
    </div>
  );
}

export default App;
