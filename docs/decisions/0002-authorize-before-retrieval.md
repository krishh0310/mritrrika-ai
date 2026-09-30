# ADR 0002: Authorize before retrieving records

Status: accepted.

Citizen and officer queries first resolve the principal and permitted parcel scope, then query only records inside that scope. A post-query filter could retrieve hidden records into a language-model context or log, even if the final response hid them. Keep the access predicate in API service queries and return 404 for out-of-scope objects where existence itself is sensitive. The citizen isolation and prompt-injection tests exercise this boundary.
