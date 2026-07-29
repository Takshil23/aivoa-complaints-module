/** Copilot transcript, streaming state, and the bonus-AI result panel. */

import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import * as api from '../api/client';
import { applyAgentResult, bootstrapSession, resetComplaint } from './complaintSlice';

const initialState = {
  messages: [],
  isStreaming: false,
  /** { label, progress } while a turn is in flight, else null */
  progress: null,
  error: null,
  aiFeature: { name: null, loading: false, result: null, error: null },
};

/** Shared handler for both stream endpoints. */
function makeEventHandler(dispatch) {
  return (event) => {
    switch (event.type) {
      case 'user_message':
        dispatch(chatSlice.actions.appendMessage(event.message));
        break;
      case 'status':
        dispatch(
          chatSlice.actions.setProgress({
            label: event.label,
            progress: event.progress,
          }),
        );
        break;
      case 'result':
        if (event.message) dispatch(chatSlice.actions.appendMessage(event.message));
        dispatch(applyAgentResult(event));
        break;
      case 'error':
        dispatch(chatSlice.actions.setChatError(event.message));
        break;
      case 'done':
        dispatch(chatSlice.actions.setProgress(null));
        break;
      default:
        break;
    }
  };
}

export const sendMessage = createAsyncThunk(
  'chat/sendMessage',
  async (message, { dispatch, getState, rejectWithValue }) => {
    const sessionId = getState().complaint.sessionId;
    try {
      await api.streamChat({ sessionId, message }, makeEventHandler(dispatch));
    } catch (err) {
      return rejectWithValue(err.message);
    }
    return true;
  },
);

export const uploadDocument = createAsyncThunk(
  'chat/uploadDocument',
  async (file, { dispatch, getState, rejectWithValue }) => {
    const sessionId = getState().complaint.sessionId;
    try {
      await api.streamUpload({ sessionId, file }, makeEventHandler(dispatch));
    } catch (err) {
      return rejectWithValue(err.message);
    }
    return true;
  },
);

export const runAiFeature = createAsyncThunk(
  'chat/aiFeature',
  async (feature, { getState, rejectWithValue }) => {
    try {
      const data = await api.runAiFeature(feature, getState().complaint.sessionId);
      return { feature, result: data.result };
    } catch (err) {
      return rejectWithValue({ feature, message: err.message });
    }
  },
);

const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    appendMessage(state, action) {
      const incoming = action.payload;
      if (state.messages.some((m) => m.id === incoming.id)) return;
      state.messages.push(incoming);
    },
    setProgress(state, action) {
      state.progress = action.payload;
    },
    setChatError(state, action) {
      state.error = action.payload;
      state.progress = null;
    },
    clearChatError(state) {
      state.error = null;
    },
    closeAiFeature(state) {
      state.aiFeature = { name: null, loading: false, result: null, error: null };
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(bootstrapSession.fulfilled, (state, action) => {
        state.messages = action.payload.messages || [];
      })
      .addCase(resetComplaint.fulfilled, (state, action) => {
        state.messages = action.payload.messages || [];
        state.error = null;
        state.progress = null;
      })
      .addCase(runAiFeature.pending, (state, action) => {
        state.aiFeature = {
          name: action.meta.arg,
          loading: true,
          result: null,
          error: null,
        };
      })
      .addCase(runAiFeature.fulfilled, (state, action) => {
        state.aiFeature = {
          name: action.payload.feature,
          loading: false,
          result: action.payload.result,
          error: null,
        };
      })
      .addCase(runAiFeature.rejected, (state, action) => {
        state.aiFeature = {
          name: action.payload?.feature ?? state.aiFeature.name,
          loading: false,
          result: null,
          error: action.payload?.message || 'That AI feature failed.',
        };
      });

    // Streaming lifecycle for both send + upload.
    for (const thunk of [sendMessage, uploadDocument]) {
      builder
        .addCase(thunk.pending, (state) => {
          state.isStreaming = true;
          state.error = null;
        })
        .addCase(thunk.fulfilled, (state) => {
          state.isStreaming = false;
          state.progress = null;
        })
        .addCase(thunk.rejected, (state, action) => {
          state.isStreaming = false;
          state.progress = null;
          state.error = action.payload || 'The request failed.';
        });
    }
  },
});

export const { clearChatError, closeAiFeature } = chatSlice.actions;
export default chatSlice.reducer;

export const selectMessages = (s) => s.chat.messages;
export const selectIsStreaming = (s) => s.chat.isStreaming;
export const selectProgress = (s) => s.chat.progress;
export const selectChatError = (s) => s.chat.error;
export const selectAiFeature = (s) => s.chat.aiFeature;
