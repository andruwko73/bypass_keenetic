# Frozen parser oracle from v1.1054; no top-level router operations.
cut_local() {
	grep -vE "$LOCAL_RE"
}

trim_line() {
	sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

append_restore() {
	tmp_set="$1"
	value="$2"
	[ -n "$tmp_set" ] && [ -n "$value" ] && printf 'add %s %s\n' "$tmp_set" "$value" >> "$restore_file"
}

extract_direct_entry() {
	line="$1"
	cidr="$(printf '%s\n' "$line" | grep -Eo "$IPV4_RE/[0-9]{1,2}" | cut_local | head -n 1)"
	if [ -n "$cidr" ]; then
		printf '%s\n' "$cidr"
		return 0
	fi

	range="$(printf '%s\n' "$line" | grep -Eo "$IPV4_RE-$IPV4_RE" | cut_local | head -n 1)"
	if [ -n "$range" ]; then
		printf '%s\n' "$range"
		return 0
	fi

	addr="$(printf '%s\n' "$line" | grep -Eo "$IPV4_RE" | cut_local | head -n 1)"
	if [ -n "$addr" ]; then
		printf '%s\n' "$addr"
		return 0
	fi

	return 1
}

extract_ipv6_direct_entry() {
	line="$(printf '%s\n' "$1" | sed 's/\r//g;s/#.*//;s/[[:space:]].*$//;s/,.*$//' | trim_line)"
	case "$line" in
		*:*)
			if printf '%s\n' "$line" | grep -Eq '^[0-9A-Fa-f:]+(/[0-9]{1,3})?$'; then
				printf '%s\n' "$line"
				return 0
			fi
			;;
	esac
	return 1
}

normalize_domain() {
	printf '%s\n' "$1" \
		| sed 's/\r//g;s/^DOMAIN-SUFFIX,//;s/^DOMAIN,//;s/^HOST-SUFFIX,//;s/^+\.//;s/^\*\.//;s/[[:space:]].*$//;s/,.*$//;s#^/##;s#/$##' \
		| trim_line
}

connectivity_check_domain() {
	domain="$(normalize_domain "$1" | tr '[:upper:]' '[:lower:]')"
	case "$domain" in
		connectivitycheck.gstatic.com|connectivitycheck.android.com|clients3.google.com|clients4.google.com|www.google.com|www.gstatic.com)
			return 0
			;;
	esac
	return 1
}

udp_quic_excluded_direct_entry() {
	direct_entry="$(printf '%s\n' "$1" | tr '[:upper:]' '[:lower:]')"
	[ -n "$direct_entry" ] || return 1
	[ -s "$UDP_QUIC_EXCLUDE_SOURCE" ] || return 1
	grep -Fx "$direct_entry" "$UDP_QUIC_EXCLUDE_SOURCE" >/dev/null 2>&1
}

udp_quic_domain() {
	domain="$(normalize_domain "$1" | tr '[:upper:]' '[:lower:]')"
	[ -n "$domain" ] || return 1
	[ -s "$UDP_QUIC_POLICY_SOURCE" ] || return 1
	awk -v domain="$domain" '
		function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
		function norm(s) {
			s=tolower(s); sub(/\r/, "", s); sub(/#.*/, "", s); s=trim(s)
			sub(/^domain-suffix,/, "", s); sub(/^domain,/, "", s); sub(/^host-suffix,/, "", s)
			sub(/^\+\./, "", s); sub(/^\*\./, "", s); sub(/\/$/, "", s)
			return s
		}
		{
			entry=norm($0)
			if (entry == "" || entry ~ /[:\/]/ || entry ~ /^[0-9.]+$/) next
			if (domain == entry || domain ~ ("\\." entry "$")) found=1
		}
		END { exit found ? 0 : 1 }
	' "$UDP_QUIC_POLICY_SOURCE"
}

udp_quic_direct_entry() {
	direct_entry="$(printf '%s\n' "$1" | tr '[:upper:]' '[:lower:]')"
	[ -n "$direct_entry" ] || return 1
	[ -s "$UDP_QUIC_POLICY_SOURCE" ] || return 1
	udp_quic_excluded_direct_entry "$direct_entry" && return 1
	awk -v direct_entry="$direct_entry" '
		function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
		{
			entry=tolower($0); sub(/\r/, "", entry); sub(/#.*/, "", entry); entry=trim(entry)
			if (entry == direct_entry && entry ~ /^[0-9.]+(\/[0-9]+)?$/) found=1
		}
		END { exit found ? 0 : 1 }
	' "$UDP_QUIC_POLICY_SOURCE"
}

load_file_to_set() {
	list_path="$1"
	set_name="$2"
	main_tmp_set="$3"
	mirror_set_name="$4"
	mirror_tmp_set="$5"
	ipv6_set_name="$6"
	ipv6_tmp_set="$7"
	prepare_temp_set "$set_name" "$main_tmp_set"
	if [ -n "$mirror_set_name" ] && [ -n "$mirror_tmp_set" ]; then
		prepare_temp_set "$mirror_set_name" "$mirror_tmp_set"
	fi
	if [ -n "$ipv6_set_name" ] && [ -n "$ipv6_tmp_set" ]; then
		prepare_temp_set "$ipv6_set_name" "$ipv6_tmp_set" inet6
	fi

	if [ ! -f "$list_path" ]; then
		: > "$tmp_dir/${set_name}.missing"
		[ -n "$mirror_set_name" ] && : > "$tmp_dir/${mirror_set_name}.missing"
		[ -n "$ipv6_set_name" ] && : > "$tmp_dir/${ipv6_set_name}.missing"
		return 0
	fi

	domain_file="$tmp_dir/${set_name}.domains"
	source_file="$tmp_dir/${set_name}.source"
	mirror_source_file="$tmp_dir/${mirror_set_name}.source"
	mirror_domain_file="$tmp_dir/${mirror_set_name}.domains"
	ipv6_source_file="$tmp_dir/${ipv6_set_name}.source"
	: > "$domain_file"
	[ -n "$mirror_set_name" ] && : > "$mirror_domain_file"

	while IFS= read -r raw_line || [ -n "$raw_line" ]; do
		line="$(printf '%s\n' "$raw_line" | trim_line)"
		case "$line" in
			''|\#*) continue ;;
		esac

		if direct_entry="$(extract_direct_entry "$line")"; then
			: > "$source_file"
			append_restore "$main_tmp_set" "$direct_entry"
			if [ -n "$mirror_set_name" ] && [ -n "$mirror_tmp_set" ] && udp_quic_direct_entry "$direct_entry"; then
				: > "$mirror_source_file"
				append_restore "$mirror_tmp_set" "$direct_entry"
			fi
			continue
		fi

		if direct_ipv6_entry="$(extract_ipv6_direct_entry "$line")"; then
			[ -n "$ipv6_tmp_set" ] && : > "$ipv6_source_file"
			append_restore "$ipv6_tmp_set" "$direct_ipv6_entry"
			continue
		fi

		domain="$(normalize_domain "$line")"
		if [ -n "$domain" ]; then
			connectivity_check_domain "$domain" && continue
			: > "$source_file"
			printf '%s\n' "$domain" >> "$domain_file"
			[ -n "$ipv6_set_name" ] && : > "$ipv6_source_file"
			if [ -n "$mirror_set_name" ] && udp_quic_domain "$domain"; then
				: > "$mirror_source_file"
				printf '%s\n' "$domain" >> "$mirror_domain_file"
			fi
		fi
	done < "$list_path"

	resolve_domains "$main_tmp_set" "$domain_file" "$mirror_tmp_set" "$mirror_domain_file"
	resolve_ipv6_domains "$ipv6_tmp_set" "$domain_file"
}
