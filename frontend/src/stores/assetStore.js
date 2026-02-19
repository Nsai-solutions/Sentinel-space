import { create } from 'zustand';
import { fetchAssets, addAsset, deleteAsset, getAsset } from '../api/client';

const useAssetStore = create((set, get) => ({
  assets: [],
  selectedAssetId: null,
  selectedAssetDetail: null,
  loading: false,
  error: null,

  loadAssets: async () => {
    set({ loading: true, error: null });
    try {
      const res = await fetchAssets();
      set({ assets: Array.isArray(res.data) ? res.data : [], loading: false });
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
    set({ selectedAssetId: id, selectedAssetDetail: null });
    if (id) {
      try {
        const res = await getAsset(id);
        set({ selectedAssetDetail: res.data });
      } catch (err) {
        console.error('Failed to load asset detail:', err);
      }
    }
  },

  clearSelection: () => set({ selectedAssetId: null, selectedAssetDetail: null }),
}));

export default useAssetStore;
