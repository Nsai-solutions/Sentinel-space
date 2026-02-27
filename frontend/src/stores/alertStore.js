import { create } from 'zustand';
import { fetchAlerts, getUnreadCount, acknowledgeAlert, markAllAlertsRead } from '../api/client';

const useAlertStore = create((set) => ({
  alerts: [],
  unreadCount: 0,
  loading: false,

  loadAlerts: async (params = {}) => {
    set({ loading: true });
    try {
      const res = await fetchAlerts(params);
      set({ alerts: Array.isArray(res.data) ? res.data : [], loading: false });
    } catch (err) {
      set({ loading: false });
    }
  },

  loadUnreadCount: async () => {
    try {
      const res = await getUnreadCount();
      set({ unreadCount: typeof res.data?.unread === 'number' ? res.data.unread : 0 });
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

  markAllRead: async () => {
    try {
      await markAllAlertsRead();
      set((state) => ({
        alerts: state.alerts.map((a) => ({ ...a, status: 'ACKNOWLEDGED' })),
        unreadCount: 0,
      }));
    } catch (err) {
      console.error('Failed to mark all read:', err);
    }
  },
}));

export default useAlertStore;
