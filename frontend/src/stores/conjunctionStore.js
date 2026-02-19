import { create } from 'zustand';
import { fetchConjunctions, getConjunction, getConjunctionSummary, runScreening, getScreeningStatus } from '../api/client';

const useConjunctionStore = create((set, get) => ({
  conjunctions: [],
  selectedConjunctionId: null,
  selectedConjunction: null,
  summary: { total: 0, by_level: {} },
  loading: false,
  screening: {
    active: false,
    jobId: null,
    progress: 0,
    status: null,
    totalObjects: 0,
    candidatesFound: 0,
    conjunctionsFound: 0,
    error: null,
    statusText: '',
  },

  loadConjunctions: async (params = {}) => {
    set({ loading: true });
    try {
      const res = await fetchConjunctions(params);
      set({ conjunctions: Array.isArray(res.data) ? res.data : [], loading: false });
    } catch (err) {
      set({ loading: false });
    }
  },

  loadSummary: async () => {
    try {
      const res = await getConjunctionSummary();
      const data = res.data;
      set({ summary: (data && typeof data === 'object' && !Array.isArray(data)) ? data : { total: 0, by_level: {} } });
    } catch (err) {
      console.error('Failed to load summary:', err);
    }
  },

  selectConjunction: async (id) => {
    set({ selectedConjunctionId: id, selectedConjunction: null });
    if (id) {
      try {
        const res = await getConjunction(id);
        set({ selectedConjunction: res.data });
      } catch (err) {
        console.error('Failed to load conjunction:', err);
      }
    }
  },

  startScreening: async (assetIds, config = {}) => {
    set({
      screening: {
        active: true,
        jobId: null,
        progress: 0,
        status: 'STARTING',
        totalObjects: 0,
        candidatesFound: 0,
        conjunctionsFound: 0,
        error: null,
        statusText: 'Initiating screening...',
      },
    });
    try {
      const res = await runScreening({
        asset_ids: assetIds,
        time_window_days: config.timeWindowDays || 7,
        distance_threshold_km: config.distanceThreshold || 25,
      });
      const jobId = res.data.jobs?.[0]?.job_id;
      if (!jobId) {
        set({
          screening: {
            active: false, jobId: null, progress: 0,
            status: 'FAILED', totalObjects: 0, candidatesFound: 0, conjunctionsFound: 0,
            error: 'No screening jobs created',
            statusText: 'Failed: no assets to screen',
          },
        });
        return res.data;
      }
      set({
        screening: {
          ...get().screening,
          jobId,
          statusText: 'Screening started, scanning catalog...',
        },
      });
      get().pollScreeningStatus(jobId);
      return res.data;
    } catch (err) {
      const msg = err.response?.data?.detail || err.message;
      set({
        screening: {
          active: false, jobId: null, progress: 0,
          status: 'FAILED', totalObjects: 0, candidatesFound: 0, conjunctionsFound: 0,
          error: msg, statusText: `Error: ${msg}`,
        },
      });
      throw err;
    }
  },

  pollScreeningStatus: async (jobId) => {
    const poll = async () => {
      try {
        const res = await getScreeningStatus(jobId);
        const d = res.data;

        let statusText = '';
        if (d.status === 'PENDING') {
          statusText = 'Waiting to start...';
        } else if (d.status === 'RUNNING') {
          const pct = Math.round((d.progress || 0) * 100);
          if (d.progress < 0.11) {
            statusText = `Coarse filter: scanning ${d.total_objects} objects...`;
          } else {
            statusText = `Fine screening ${pct}%: ${d.candidates_found} candidates, ${d.conjunctions_found} conjunctions`;
          }
        } else if (d.status === 'COMPLETED') {
          if (d.conjunctions_found === 0 && d.error_message) {
            statusText = `No conjunctions — ${d.error_message}`;
          } else {
            statusText = `Complete: ${d.conjunctions_found} conjunction${d.conjunctions_found !== 1 ? 's' : ''} found`;
          }
        } else if (d.status === 'FAILED') {
          statusText = `Failed: ${d.error_message || 'unknown error'}`;
        }

        set({
          screening: {
            active: d.status === 'RUNNING' || d.status === 'PENDING',
            jobId,
            progress: d.progress || 0,
            status: d.status,
            totalObjects: d.total_objects || 0,
            candidatesFound: d.candidates_found || 0,
            conjunctionsFound: d.conjunctions_found || 0,
            error: d.error_message || null,
            statusText,
          },
        });

        if (d.status === 'RUNNING' || d.status === 'PENDING') {
          setTimeout(poll, 1500);
        } else {
          get().loadConjunctions();
          get().loadSummary();
        }
      } catch (err) {
        set({
          screening: {
            active: false, jobId: null, progress: 0,
            status: 'FAILED', totalObjects: 0, candidatesFound: 0, conjunctionsFound: 0,
            error: err.message, statusText: `Connection error: ${err.message}`,
          },
        });
      }
    };
    poll();
  },

  clearSelection: () => set({ selectedConjunctionId: null, selectedConjunction: null }),
}));

export default useConjunctionStore;
