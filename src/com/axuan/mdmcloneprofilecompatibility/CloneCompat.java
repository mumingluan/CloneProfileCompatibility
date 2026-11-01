// SPDX-License-Identifier: Apache-2.0
package com.axuan.mdmcloneprofilecompatibility;

import android.os.UserHandle;
import android.util.Log;
import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/** Compatibility for AxuanMDM Device Owner on the tested OPPO Android 16 ROM. */
public final class CloneCompat implements IXposedHookLoadPackage {
    private static final String TAG = "AxuanMDMCloneProfile";
    private static final String OWNER = "com.axuan.mdm";
    private static final String KEY = "no_add_clone_profile";
    private static final String POLICY = "com.android.server.devicepolicy.DevicePolicyManagerService";
    private static volatile Object policyService;

    private static void log(String message) {
        Log.i(TAG, message);
        XposedBridge.log(TAG + ": " + message);
    }

    private static boolean hasAxuanOwner() {
        Object service = policyService;
        if (service == null) return false;
        try {
            Object owners = XposedHelpers.getObjectField(service, "mOwners");
            return OWNER.equals(XposedHelpers.callMethod(owners, "getDeviceOwnerPackageName"))
                    && Integer.valueOf(0).equals(XposedHelpers.callMethod(owners, "getDeviceOwnerUserId"));
        } catch (Throwable error) {
            return false;
        }
    }

    private static boolean isAutomaticPolicyCall() {
        for (StackTraceElement frame : Thread.currentThread().getStackTrace()) {
            if (!POLICY.equals(frame.getClassName())) continue;
            String method = frame.getMethodName();
            if ("applyProfileRestrictionsIfDeviceOwnerLocked".equals(method)
                    || method.startsWith("lambda$setDeviceOwner$")) return true;
        }
        return false;
    }

    private static void clearBaseRestriction(Object service, String reason) {
        policyService = service;
        if (!hasAxuanOwner()) return;
        try {
            Object manager = XposedHelpers.getObjectField(service, "mUserManager");
            UserHandle primary = (UserHandle) XposedHelpers.callStaticMethod(UserHandle.class, "of", 0);
            if (Boolean.TRUE.equals(XposedHelpers.callMethod(manager, "hasUserRestriction", KEY, primary))) {
                XposedHelpers.callMethod(manager, "setUserRestriction", KEY, false, primary);
                log("Cleared primary-user clone base restriction: " + reason);
            }
        } catch (Throwable error) {
            log("Cannot clear clone base restriction: " + error);
        }
    }

    @Override public void handleLoadPackage(XC_LoadPackage.LoadPackageParam packageParam) {
        if (!"android".equals(packageParam.packageName) || !"android".equals(packageParam.processName)) return;
        try {
            Class<?> policy = XposedHelpers.findClass(POLICY, packageParam.classLoader);
            XposedBridge.hookAllConstructors(policy, new XC_MethodHook() {
                @Override protected void afterHookedMethod(MethodHookParam param) {
                    if (!param.hasThrowable()) policyService = param.thisObject;
                }
            });
            XposedHelpers.findAndHookMethod("com.android.server.pm.UserManagerService", packageParam.classLoader,
                    "setUserRestriction", String.class, boolean.class, int.class, new XC_MethodHook() {
                @Override protected void beforeHookedMethod(MethodHookParam param) {
                    int userId = (Integer) param.args[2];
                    if (KEY.equals(param.args[0]) && Boolean.TRUE.equals(param.args[1])
                            && (userId == 0 || userId == 999) && hasAxuanOwner() && isAutomaticPolicyCall()) {
                        param.args[1] = false;
                        log("Allowed clone profile; skipped automatic restriction for user " + userId);
                    }
                }
            });
            XposedHelpers.findAndHookMethod(policy, "systemReady", int.class, new XC_MethodHook() {
                @Override protected void beforeHookedMethod(MethodHookParam param) {
                    if ((Integer) param.args[0] == 550) clearBaseRestriction(param.thisObject, "boot phase 550");
                }
            });
            XposedHelpers.findAndHookMethod(policy, "applyProfileRestrictionsIfDeviceOwnerLocked", new XC_MethodHook() {
                @Override protected void beforeHookedMethod(MethodHookParam param) {
                    clearBaseRestriction(param.thisObject, "automatic profile restrictions");
                }
            });
            log("v1.0.1 hooks installed in system_server");
        } catch (Throwable error) {
            log("Hook installation failed: " + error);
        }
    }
}
