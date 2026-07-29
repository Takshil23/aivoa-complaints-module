import { configureStore } from '@reduxjs/toolkit';
import complaintReducer from './complaintSlice';
import chatReducer from './chatSlice';

export const store = configureStore({
  reducer: {
    complaint: complaintReducer,
    chat: chatReducer,
  },
});
