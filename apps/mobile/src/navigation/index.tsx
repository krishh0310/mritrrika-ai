/**
 * The two mobile experiences, and the gate in front of them (§59).
 *
 * §4 draws the line this file enforces: the phone is a citizen portal and a
 * field-capture tool. There is no verification workspace and no approval
 * queue here, because a phone is the wrong instrument for reading OCR
 * overlays against a scan -- that work stays on the desktop.
 *
 * Which stack mounts follows from /auth/me, so it survives a restart and
 * cannot be chosen by the person holding the phone. It is still only what the
 * app SHOWS: every route behind it is authorized again on the server (§62).
 */

import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { ActivityIndicator, View } from "react-native";

import { useAuth } from "../auth/auth-context";
import { UiLanguageProvider, useT, type UiLanguage } from "../i18n";
import { colors } from "../theme";
import { DesktopOnlyScreen } from "../screens/DesktopOnlyScreen";
import { LoginScreen } from "../screens/LoginScreen";
import { AssistantScreen } from "../screens/citizen/AssistantScreen";
import { CitizenDashboardScreen } from "../screens/citizen/CitizenDashboardScreen";
import { CitizenMapScreen } from "../screens/citizen/CitizenMapScreen";
import { CitizenRecordScreen } from "../screens/citizen/CitizenRecordScreen";
import { CitizenSearchScreen } from "../screens/citizen/CitizenSearchScreen";
import { GrievancesScreen } from "../screens/citizen/GrievancesScreen";
import { MyLandScreen } from "../screens/citizen/MyLandScreen";
import { CameraUploadScreen } from "../screens/deo/CameraUploadScreen";
import { FieldHomeScreen } from "../screens/deo/FieldHomeScreen";
import { OfflineQueueScreen } from "../screens/deo/OfflineQueueScreen";
import { UploadMetadataScreen } from "../screens/deo/UploadMetadataScreen";
import { UploadStatusScreen } from "../screens/deo/UploadStatusScreen";

export type CitizenStackParams = {
  CitizenDashboard: undefined;
  MyLand: undefined;
  CitizenSearch: undefined;
  CitizenRecord: { parcelId: string; khasra?: string };
  CitizenMap: { villageId?: string; villageName?: string; highlight?: string } | undefined;
  Grievances: { parcelId?: string; khasra?: string } | undefined;
  Assistant: undefined;
};

export type FieldStackParams = {
  FieldHome: undefined;
  CameraUpload: undefined;
  /** `uri` is the compressed capture on disk; nothing is queued until this screen submits. */
  UploadMetadata: { uri: string; fileName: string };
  UploadStatus: { queueId: string };
  OfflineQueue: undefined;
};

export type AuthStackParams = {
  Login: undefined;
};

export type DesktopStackParams = {
  DesktopOnly: undefined;
};

const CitizenStack = createNativeStackNavigator<CitizenStackParams>();
const FieldStack = createNativeStackNavigator<FieldStackParams>();
const AuthStack = createNativeStackNavigator<AuthStackParams>();
const DesktopStack = createNativeStackNavigator<DesktopStackParams>();

const screenOptions = {
  headerStyle: { backgroundColor: colors.navy },
  headerTintColor: colors.white,
  headerTitleStyle: { fontSize: 16, fontWeight: "600" as const },
  headerBackTitle: "Back",
  contentStyle: { backgroundColor: colors.offwhite },
};

function CitizenRoutes() {
  const t = useT();
  return (
    <CitizenStack.Navigator screenOptions={screenOptions}>
      <CitizenStack.Screen
        name="CitizenDashboard"
        component={CitizenDashboardScreen}
        options={{ title: t("app.name") }}
      />
      <CitizenStack.Screen
        name="MyLand"
        component={MyLandScreen}
        options={{ title: t("citizen.myLand.title") }}
      />
      <CitizenStack.Screen
        name="CitizenSearch"
        component={CitizenSearchScreen}
        options={{ title: t("citizen.search.title") }}
      />
      <CitizenStack.Screen
        name="CitizenRecord"
        component={CitizenRecordScreen}
        options={({ route }) => ({
          title: route.params.khasra
            ? `${t("citizen.myLand.khasra")} ${route.params.khasra}`
            : t("record.title"),
        })}
      />
      <CitizenStack.Screen
        name="CitizenMap"
        component={CitizenMapScreen}
        options={{ title: t("citizen.map.heading") }}
      />
      <CitizenStack.Screen
        name="Grievances"
        component={GrievancesScreen}
        options={{ title: t("citizen.grievances.title") }}
      />
      <CitizenStack.Screen
        name="Assistant"
        component={AssistantScreen}
        options={{ title: t("citizen.assistant.heading") }}
      />
    </CitizenStack.Navigator>
  );
}

function FieldRoutes() {
  return (
    <FieldStack.Navigator screenOptions={screenOptions}>
      <FieldStack.Screen
        name="FieldHome"
        component={FieldHomeScreen}
        options={{ title: "Field capture" }}
      />
      <FieldStack.Screen
        name="CameraUpload"
        component={CameraUploadScreen}
        options={{ title: "Capture document", headerShown: false }}
      />
      <FieldStack.Screen
        name="UploadMetadata"
        component={UploadMetadataScreen}
        options={{ title: "Record details" }}
      />
      <FieldStack.Screen
        name="UploadStatus"
        component={UploadStatusScreen}
        options={{ title: "Upload status" }}
      />
      <FieldStack.Screen
        name="OfflineQueue"
        component={OfflineQueueScreen}
        options={{ title: "Upload queue" }}
      />
    </FieldStack.Navigator>
  );
}

function DesktopRoutes() {
  return (
    <DesktopStack.Navigator screenOptions={screenOptions}>
      <DesktopStack.Screen
        name="DesktopOnly"
        component={DesktopOnlyScreen}
        options={{ title: "Mrittika AI" }}
      />
    </DesktopStack.Navigator>
  );
}

function Splash() {
  return (
    <View
      style={{
        flex: 1,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: colors.navy,
      }}
    >
      <ActivityIndicator size="large" color={colors.warm} />
    </View>
  );
}

export function RootNavigator() {
  const { user, loading, experience } = useAuth();

  // Citizens read Hindi by default -- the portal is public-facing and the
  // records are in Hindi. Field and desktop experiences default to English,
  // the revenue service's working language. A stored choice overrides both.
  const defaultLanguage: UiLanguage = experience === "CITIZEN" ? "hi" : "en";

  // Hold the splash until /auth/me settles. Mounting the login stack first and
  // swapping it out a moment later would flash a sign-in form at a user who is
  // already signed in.
  if (loading) return <Splash />;

  return (
    <UiLanguageProvider defaultLanguage={defaultLanguage}>
    <NavigationContainer>
      {!user ? (
        <AuthStack.Navigator screenOptions={{ headerShown: false }}>
          <AuthStack.Screen name="Login" component={LoginScreen} />
        </AuthStack.Navigator>
      ) : experience === "CITIZEN" ? (
        <CitizenRoutes />
      ) : experience === "FIELD" ? (
        <FieldRoutes />
      ) : (
        <DesktopRoutes />
      )}
    </NavigationContainer>
    </UiLanguageProvider>
  );
}
