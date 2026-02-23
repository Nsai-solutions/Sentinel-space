import { create } from 'zustand';
import { fetchAssets, addAsset, deleteAsset, getAsset } from '../api/client';

const useAssetStore = create((set, get) => ({
  assets: [],
  selectedAssetId: null,
  selectedAssetDetail: null,
  loading: false,
  error: null,
  _pollInterval: null,

  loadAssets: async () => {
    set({ loading: true, error: null });
    try {
      const res = await fetchAssets();
      const newAssets = Array.isArray(res.data) ? res.data : [];
      const currentSelectedId = get().selectedAssetId;

      // If selected asset no longer exists in new list, clear selection
      const selectedStillExists = currentSelectedId && newAssets.some(a => a.id === currentSelectedId);

      set({
        assets: newAssets,
        loading: false,
        ...(selectedStillExists ? {} : { selectedAssetId: null, selectedAssetDetail: null }),
      });

      // Clear polling if selection was invalidated
      if (!selectedStillExists && get()._pollInterval) {
        clearInterval(get()._pollInterval);
        set({ _pollInterval: null });
      }
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  addAsset: async (data) => {
    try {
      const res = await addAsset(data);
      set((state) => ({ assets: [...state.assets, res.data] }));
      return res.data;
    } catch (err) {
      throw err;
    }
  },

  removeAsset: async (id) => {
    try {
      await deleteAsset(id);
      set((state) => ({
        assets: state.assets.filter((a) => a.id !== id),
        selectedAssetId: state.selectedAssetId === id ? null : state.selectedAssetId,
      }));
    } catch (err) {
      throw err;
    }
  },

  selectAsset: async (id) => {
    // Clear any existing poll
    const prev = get()._pollInterval;
    if (prev) clearInterval(prev);

    set({ selectedAssetId: id, selectedAssetDetail: null, _pollInterval: null });

    if (id) {
      // Initial fetch
      try {
        const res = await getAsset(id);
        set({ selectedAssetDetail: res.data });
      } catch (err) {
        console.error('Failed to load asset detail:', err);
        // Fallback: use basic asset data already in the store
        const asset = get().assets.find((a) => a.id === id);
        if (asset) set({ selectedAssetDetail: asset });
      }

      // Start polling every 3 seconds for live position updates
      let pollFailCount = 0;
      const interval = setInterval(async () => {
        if (get().selectedAssetId !== id) {
          clearInterval(interval);
          return;
        }
        try {
          const res = await getAsset(id);
          set({ selectedAssetDetail: res.data });
          pollFailCount = 0;
        } catch (err) {
          pollFailCount++;
          // Stop polling after 3 consecutive failures (likely 404 from cold start)
          if (pollFailCount >= 3 || err?.response?.status === 404) {
            clearInterval(interval);
            set({ _pollInterval: null });
          }
        }
      }, 3000);

      set({ _pollInterval: interval });
    }
  },

  clearSelection: () => {
    const prev = get()._pollInterval;
    if (prev) clearInterval(prev);
    set({ selectedAssetId: null, selectedAssetDetail: null, _pollInterval: null });
  },
}));

export default useAssetStore;
