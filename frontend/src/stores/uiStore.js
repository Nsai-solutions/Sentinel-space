import { create } from 'zustand';

const useUIStore = create((set) => ({
  // Panel visibility
  bottomPanelExpanded: true,
  bottomPanelTab: 'table', // 'table' | 'timeline' | 'analytics'
  rightPanelMode: 'asset', // 'asset' | 'conjunction'

  // Simulation
  simTime: new Date().toISOString(),
  isPlaying: true,
  warpFactor: 1,

  // View options
  showDebrisField: false,
  showGroundTracks: false,
  showLabels: true,
  showOrbits: true,

  // Actions
  toggleBottomPanel: () => set((s) => ({ bottomPanelExpanded: !s.bottomPanelExpanded })),
  setBottomPanelTab: (tab) => set({ bottomPanelTab: tab }),
  setRightPanelMode: (mode) => set({ rightPanelMode: mode }),
  setSimTime: (time) => set({ simTime: time }),
  togglePlaying: () => set((s) => ({ isPlaying: !s.isPlaying })),
  setWarpFactor: (f) => set({ warpFactor: f }),
  toggleDebrisField: () => set((s) => ({ showDebrisField: !s.showDebrisField })),
  toggleGroundTracks: () => set((s) => ({ showGroundTracks: !s.showGroundTracks })),
  toggleLabels: () => set((s) => ({ showLabels: !s.showLabels })),
  toggleOrbits: () => set((s) => ({ showOrbits: !s.showOrbits })),
}));

export default useUIStore;
