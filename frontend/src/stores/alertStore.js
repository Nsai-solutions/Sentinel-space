import { create } from 'zustand';
import { fetchAlerts, getUnreadCount, acknowledgeAlert } from '../api/client';

const useAlertStore = create((set) => ({
  alerts: [],
  unreadCount: 0,
  loading: false,

  loadAlerts: async (params = {}) => {
    set({ loading: true });
    try {
      const res = await fetchAlerts(params);
      set({ alerts: res.data, loading: false });
    } catch (err) {
      set({ loading: false });
    }
  },

  loadUnreadCount: async () => {
    try {
      const res = await getUnreadCount();
      set({ unreadCount: res.data.unread });
    } catch (err) {
      console.error('Failed to load unread count:', err);
    }
  },

  acknowledge: async (id) => {
    try {
      await acknowledgeAlert(id);
      set((state) => ({
        alerts: state.alerts.map((a) =>
          a.id === id ? { ...a, status: 'ACKNOWLEDGED' } : a
        ),
        unreadCount: Math.max(0, state.unreadCount - 1),
      }));
    } catch (err) {
      throw err;
    }
  },
}));

export default useAlertStore;
