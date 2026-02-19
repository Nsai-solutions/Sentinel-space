import useAssetStore from '../../stores/assetStore';
import useConjunctionStore from '../../stores/conjunctionStore';
import useUIStore from '../../stores/uiStore';
import AssetDetail from '../modules/AssetDetail';
import ConjunctionDetail from '../modules/ConjunctionDetail';
import './RightPanel.css';

export default function RightPanel() {
  const rightPanelMode = useUIStore((s) => s.rightPanelMode);
  const selectedAssetDetail = useAssetStore((s) => s.selectedAssetDetail);
  const selectedConjunction = useConjunctionStore((s) => s.selectedConjunction);

  const hasContent = rightPanelMode === 'asset' ? selectedAssetDetail : selectedConjunction;

  return (
    <aside className="right-panel">
      {rightPanelMode === 'conjunction' && selectedConjunction ? (
        <ConjunctionDetail data={selectedConjunction} />
      ) : selectedAssetDetail ? (
        <AssetDetail data={selectedAssetDetail} />
      ) : (
        <div className="right-panel-empty">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" strokeWidth="1">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4l3 3" />
          </svg>
          <p>Select an asset or conjunction to view details</p>
        </div>
      )}
    </aside>
  );
}
