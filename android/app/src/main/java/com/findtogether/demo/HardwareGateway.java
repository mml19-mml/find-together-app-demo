package com.findtogether.demo;

/** Contract only. A real vendor BLE/cellular adapter has not been implemented. */
public interface HardwareGateway {
    void pair(String deviceId, Callback callback);
    void stop();
    interface Callback {
        void onStatus(String deviceId, String status);
        void onLocation(String deviceId, String timestampIso8601, double latitude, double longitude, float accuracyMeters);
        void onError(String code, String message);
    }
}
