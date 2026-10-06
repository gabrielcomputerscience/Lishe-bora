export type RoleGrant = { role: string; role_name: string; org_id: string | null; org_name: string | null; org_type: string | null };
export type Me = {
  id: string; full_name: string; email: string | null; phone: string | null; status: string;
  preferred_language: string; mfa_enabled: boolean; roles: RoleGrant[]; permissions: string[]; supplier_id: string | null;
  is_admin: boolean; is_super_admin: boolean; menu?: string[];
};
export type TokenOut = { access_token?: string | null; mfa_required: boolean; mfa_token?: string | null; sent_to?: string | null; dev_code?: string | null };
export type Notice = { reference: string; title: string; method: string; county: string | null; eligibility: string; closes_at: string; status: string };
export type NewsItem = { slug: string; title: string; category: string; summary: string; cover_image: string; cover_alt: string; published_at: string | null; body?: string };
export type SupplierDoc = { id: string; doc_type: string; version: number; file_name: string; size_bytes: number; issued_on: string | null; expires_on: string | null; status: string; review_note: string; created_at: string };
export type Supplier = {
  id: string; organization_id: string; county_id: string | null; county_name: string | null; supplier_type: string;
  legal_name: string; registration_no: string; phone: string; email: string; sub_county: string; commodities: string[];
  approved_categories: string[]; members_count: number | null; inclusion_claim: Record<string, unknown>;
  inclusion_consent: boolean; inclusion_verified: boolean; status: string; status_note: string;
  prequalified_until: string | null; created_at: string; documents: SupplierDoc[];
};
export type Paged<T> = { total: number; items: T[] };

export type FoodCategory = { key: string; label: string; group: string; commodities: { code: string; name: string; unit: string }[] };
