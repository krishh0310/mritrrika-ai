/** The field names the API emits, in the words an officer uses. */
export const FIELD_LABELS: Record<string, string> = {
  OWNER: "Owner name",
  GUARDIAN: "Guardian name",
  KHASRA: "Khasra number",
  KHATA: "Khata number",
  VILLAGE: "Village",
  TEHSIL: "Tehsil",
  DISTRICT: "District",
  STATE: "State",
  AREA: "Area",
  AREA_UNIT: "Area unit",
  LAND_CLASS: "Land classification",
  MUTATION: "Mutation number",
  DATE: "Date",
  SHARE: "Share",
  REMARK: "Remark",
};

/** An extracted field's name as an officer says it; unknown names fall back readably. */
export function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field.replaceAll("_", " ").toLowerCase();
}
