/**
 * The complaint record: the form schema returned by the agent, the AI risk
 * assessment, and the triage status.
 *
 * The form holds no hardcoded field list — `sections` is whatever the agent sent,
 * which is how the UI reproduces the demo's changing sections and labels.
 */

import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import * as api from '../api/client';

const initialState = {
  sessionId: null,
  sections: [],
  risk: {},
  status: 'pending_triage',
  llmEnabled: false,
  models: {},
  /** field keys touched by the most recent agent turn — drives the flash highlight */
  recentlyChanged: [],
  committing: false,
  lastCommitted: null,
  error: null,
  ledger: [],
};

export const bootstrapSession = createAsyncThunk(
  'complaint/bootstrap',
  async (_, { rejectWithValue }) => {
    try {
      const stored = localStorage.getItem('aivoa.sessionId');
      const data = await api.openSession(stored);
      localStorage.setItem('aivoa.sessionId', data.sessionId);
      return data;
    } catch (err) {
      return rejectWithValue(err.message);
    }
  },
);

export const commitToLedger = createAsyncThunk(
  'complaint/commit',
  async (_, { getState, rejectWithValue }) => {
    try {
      return await api.commitComplaint(getState().complaint.sessionId);
    } catch (err) {
      return rejectWithValue(err.message);
    }
  },
);

export const resetComplaint = createAsyncThunk(
  'complaint/reset',
  async (_, { getState, rejectWithValue }) => {
    try {
      return await api.resetSession(getState().complaint.sessionId);
    } catch (err) {
      return rejectWithValue(err.message);
    }
  },
);

export const loadLedger = createAsyncThunk('complaint/ledger', async () => {
  const data = await api.fetchLedger();
  return data.complaints;
});

const complaintSlice = createSlice({
  name: 'complaint',
  initialState,
  reducers: {
    /** Applied when a chat/upload stream delivers a `result` frame. */
    applyAgentResult(state, action) {
      const { formSections, risk, status, patch } = action.payload;
      if (formSections) state.sections = formSections;
      if (risk) state.risk = risk;
      if (status) state.status = status;
      state.recentlyChanged = patch ? Object.keys(patch) : [];
      state.error = null;
    },
    clearRecentlyChanged(state) {
      state.recentlyChanged = [];
    },
    /**
     * Local edit of a field. The assignment requires the form be driven by the
     * copilot, so inputs are read-only in the UI; this exists only for the
     * explicit "unlock" escape hatch and keeps Redux the single source of truth.
     */
    setFieldValue(state, action) {
      const { key, value } = action.payload;
      for (const section of state.sections) {
        for (const field of section.fields) {
          if (field.key === key) field.value = value;
        }
      }
    },
    dismissCommit(state) {
      state.lastCommitted = null;
    },
    setError(state, action) {
      state.error = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(bootstrapSession.fulfilled, (state, action) => {
        const { sessionId, formSections, risk, status, llmEnabled, models } =
          action.payload;
        state.sessionId = sessionId;
        state.sections = formSections || [];
        state.risk = risk || {};
        state.status = status;
        state.llmEnabled = Boolean(llmEnabled);
        state.models = models || {};
        state.error = null;
      })
      .addCase(bootstrapSession.rejected, (state, action) => {
        state.error = action.payload || 'Could not reach the backend.';
      })
      .addCase(commitToLedger.pending, (state) => {
        state.committing = true;
        state.error = null;
      })
      .addCase(commitToLedger.fulfilled, (state, action) => {
        state.committing = false;
        state.lastCommitted = action.payload.complaint;
        const session = action.payload.session;
        state.sections = session.formSections || [];
        state.risk = session.risk || {};
        state.status = session.status;
        state.recentlyChanged = [];
      })
      .addCase(commitToLedger.rejected, (state, action) => {
        state.committing = false;
        state.error = action.payload || 'Commit failed.';
      })
      .addCase(resetComplaint.fulfilled, (state, action) => {
        state.sections = action.payload.formSections || [];
        state.risk = action.payload.risk || {};
        state.status = action.payload.status;
        state.recentlyChanged = [];
        state.lastCommitted = null;
        state.error = null;
      })
      .addCase(loadLedger.fulfilled, (state, action) => {
        state.ledger = action.payload;
      });
  },
});

export const {
  applyAgentResult,
  clearRecentlyChanged,
  setFieldValue,
  dismissCommit,
  setError,
} = complaintSlice.actions;

export default complaintSlice.reducer;

// --- selectors ---
export const selectSections = (s) => s.complaint.sections;
export const selectRisk = (s) => s.complaint.risk;
export const selectStatus = (s) => s.complaint.status;
export const selectSessionId = (s) => s.complaint.sessionId;
export const selectRecentlyChanged = (s) => s.complaint.recentlyChanged;

export const selectHasComplaint = (s) =>
  s.complaint.sections.some((section) =>
    section.fields.some((f) => f.value && String(f.value).trim() !== ''),
  );
