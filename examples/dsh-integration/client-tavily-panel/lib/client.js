window.__ModuleLoader__.load({
	id: "dsh-client-tavily-panel",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		var react = require("react");
		var jsx = require("react/jsx-runtime");

		var BASE = "http://127.0.0.1:8000";

		function api(path, opts) {
			return fetch(BASE + path, opts).then(function (r) {
				if (!r.ok) throw new Error("HTTP " + r.status);
				return r.json();
			});
		}

		// ---- shared inline styles (kept simple; follows the dark settings surface) ----
		var styles = {
			section: { padding: "4px 0 24px" },
			title: { fontSize: 16, fontWeight: 600, margin: "0 0 4px", color: "#e5e7eb" },
			intro: { margin: "0 0 16px", fontSize: 13, color: "#9ca3af" },
			error: { color: "#f87171", fontSize: 13, margin: "0 0 12px" },
			msg: { color: "#4ade80", fontSize: 13, margin: "0 0 12px" },
			cards: { display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" },
			card: {
				background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)",
				borderRadius: 12, padding: "10px 16px", minWidth: 110
			},
			cardValue: { fontSize: 20, fontWeight: 700, color: "#e5e7eb" },
			cardLabel: { fontSize: 12, color: "#9ca3af", marginTop: 2 },
			table: { width: "100%", borderCollapse: "collapse", fontSize: 13 },
			th: { textAlign: "left", padding: "6px 8px", color: "#9ca3af", fontWeight: 500, borderBottom: "1px solid rgba(255,255,255,0.14)" },
			td: { padding: "6px 8px", borderBottom: "1px solid rgba(255,255,255,0.08)", color: "#d1d5db", verticalAlign: "top" },
			rowActive: { color: "#4ade80" },
			rowDead: { color: "#f87171" },
			mono: { fontFamily: "ui-monospace, monospace", fontSize: 12 },
			btn: {
				background: "rgba(255,255,255,0.08)", color: "#e5e7eb", border: "1px solid rgba(255,255,255,0.18)",
				borderRadius: 8, padding: "4px 10px", fontSize: 12, cursor: "pointer", marginRight: 6
			},
			btnPrimary: { background: "#2563eb", borderColor: "#2563eb", color: "#fff" },
			btnDanger: { color: "#f87171", borderColor: "rgba(248,113,113,0.4)" },
			btnDisabled: { opacity: 0.5, cursor: "not-allowed" },
			textarea: {
				width: "100%", boxSizing: "border-box", minHeight: 72, background: "rgba(255,255,255,0.06)",
				border: "1px solid rgba(255,255,255,0.18)", borderRadius: 8, color: "#e5e7eb",
				fontFamily: "ui-monospace, monospace", fontSize: 12, padding: 8, resize: "vertical"
			},
			block: { marginTop: 20 },
			blockTitle: { fontSize: 14, fontWeight: 600, color: "#e5e7eb", margin: "0 0 8px" },
			hint: { fontSize: 12, color: "#9ca3af", marginTop: 6 }
		};

		function StatCard(props) {
			return jsx.jsx("div", {
				style: styles.card,
				children: [
					jsx.jsx("div", { style: styles.cardValue, children: props.value }),
					jsx.jsx("div", { style: styles.cardLabel, children: props.label })
				]
			});
		}

		function TavilySection() {
			var _s = react.useState({ status: "loading", data: null, error: null });
			var state = _s[0];
			var setState = _s[1];
			var _add = react.useState("");
			var addText = _add[0];
			var setAddText = _add[1];
			var _busy = react.useState(false);
			var busy = _busy[0];
			var setBusy = _busy[1];
			var _msg = react.useState(null);
			var msg = _msg[0];
			var setMsg = _msg[1];

			var load = react.useCallback(function () {
				setState({ status: "loading", data: null, error: null });
				api("/api/stats").then(function (d) {
					setState({ status: "ready", data: d, error: null });
				}).catch(function (e) {
					setState({ status: "error", data: null, error: String(e && e.message ? e.message : e) });
				});
			}, []);
			react.useEffect(function () { load(); }, [load]);

			function notice(text, ok) {
				setMsg({ text: text, ok: ok !== false });
			}

			function doAdd() {
				var keys = addText.split("\n").map(function (s) { return s.trim(); }).filter(Boolean);
				if (!keys.length) return;
				setBusy(true); setMsg(null);
				api("/api/keys/add", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({ keys: keys, labels: [] })
				}).then(function (r) {
					notice("已添加 " + r.added + " 个 key（" + keys.length + " 个输入，重复自动跳过）");
					setAddText("");
					load();
				}).catch(function (e) {
					notice("添加失败: " + (e && e.message ? e.message : e), false);
				}).finally(function () { setBusy(false); });
			}

			function doToggle(masked, active) {
				api(active ? "/api/keys/deactivate" : "/api/keys/activate", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({ masked: masked, reason: "settings-panel" })
				}).then(function () { notice(active ? "已停用 " + masked : "已启用 " + masked); load(); })
					.catch(function (e) { notice("操作失败: " + (e && e.message ? e.message : e), false); });
			}

			function doRemove(masked) {
				if (!window.confirm("确认移除 key " + masked + "？此操作不可恢复。")) return;
				api("/api/keys/remove", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({ masked: masked })
				}).then(function () { notice("已移除 " + masked); load(); })
					.catch(function (e) { notice("移除失败: " + (e && e.message ? e.message : e), false); });
			}

			function doHealth() {
				setBusy(true); setMsg(null);
				api("/api/health", { method: "POST" }).then(function (r) {
					var alive = r.results.filter(function (x) { return x.alive; }).length;
					notice("健康检查完成: " + alive + "/" + r.results.length + " 存活（失效 key 已自动停用）");
					load();
				}).catch(function (e) {
					notice("健康检查失败: " + (e && e.message ? e.message : e), false);
				}).finally(function () { setBusy(false); });
			}

			var data = state.data;
			return jsx.jsxs("div", {
				style: styles.section,
				children: [
					jsx.jsx("h2", { style: styles.title, children: "Tavily 号池" }),
					jsx.jsx("p", {
						style: styles.intro,
						children: "本地 Tavily API key 池（D:\\ASUS 用户目录 .dsh\\tavily-pool）——查看状态、添加/管理 key。面板服务: " + BASE
					}),
					state.status === "error" ? jsx.jsx("p", {
						style: styles.error,
						children: "无法连接面板服务 (" + state.error + ")。请确认 uvicorn dashboard 已在 " + BASE + " 运行。"
					}) : null,
					msg ? jsx.jsx("p", { style: msg.ok ? styles.msg : styles.error, children: msg.text }) : null,
					state.status === "loading" ? jsx.jsx("p", { style: styles.hint, children: "加载中…" }) : null,
					data ? jsx.jsxs("div", {
						children: [
							jsx.jsx("div", {
								style: styles.cards,
								children: [
									jsx.jsx(StatCard, { value: data.active_keys + "/" + data.total_keys, label: "活跃 Key" }),
									jsx.jsx(StatCard, { value: data.total_requests, label: "累计请求" }),
									jsx.jsx(StatCard, { value: data.total_errors, label: "累计错误" }),
									jsx.jsx(StatCard, { value: data.total_credits, label: "累计积分" })
								]
							}),
							jsx.jsxs("div", {
								style: styles.block,
								children: [
									jsx.jsx("h3", { style: styles.blockTitle, children: "Key 列表" }),
									jsx.jsxs("table", {
										style: styles.table,
										children: [
											jsx.jsx("thead", {
												children: jsx.jsx("tr", {
													children: [
														jsx.jsx("th", { style: styles.th, children: "状态" }),
														jsx.jsx("th", { style: styles.th, children: "Key（掩码）" }),
														jsx.jsx("th", { style: styles.th, children: "请求/错误/积分" }),
														jsx.jsx("th", { style: styles.th, children: "最近错误" }),
														jsx.jsx("th", { style: styles.th, children: "操作" })
													]
												})
											}),
											jsx.jsx("tbody", {
												children: data.keys.map(function (k) {
													return jsx.jsx("tr", {
														children: [
															jsx.jsx("td", {
																style: styles.td,
																children: jsx.jsx("span", {
																	style: k.is_active ? styles.rowActive : styles.rowDead,
																	children: k.is_active ? "● 活跃" : "● 停用"
																})
															}),
															jsx.jsx("td", { style: styles.td, children: jsx.jsx("span", { style: styles.mono, children: k.masked }) }),
															jsx.jsx("td", { style: styles.td, children: k.request_count + " / " + k.error_count + " / " + k.credits_used }),
															jsx.jsx("td", {
																style: styles.td,
																children: k.last_error ? jsx.jsx("span", { style: styles.rowDead, children: k.last_error.slice(0, 60) }) : "—"
															}),
															jsx.jsx("td", {
																style: styles.td,
																children: [
																	jsx.jsx("button", {
																		type: "button",
																		style: styles.btn,
																		onClick: function () { doToggle(k.masked, k.is_active); },
																		children: k.is_active ? "停用" : "启用"
																	}),
																	jsx.jsx("button", {
																		type: "button",
																		style: Object.assign({}, styles.btn, styles.btnDanger),
																		onClick: function () { doRemove(k.masked); },
																		children: "移除"
																	})
																]
															})
														]
													}, k.masked);
												})
											})
										]
									})
								]
							}),
							jsx.jsxs("div", {
								style: styles.block,
								children: [
									jsx.jsx("h3", { style: styles.blockTitle, children: "添加 API Key" }),
									jsx.jsx("textarea", {
										style: styles.textarea,
										placeholder: "每行一个 tvly- 开头的 key",
										value: addText,
										onChange: function (e) { setAddText(e.target.value); }
									}),
									jsx.jsx("div", {
										style: { marginTop: 8 },
										children: [
											jsx.jsx("button", {
												type: "button",
												style: Object.assign({}, styles.btn, styles.btnPrimary, busy ? styles.btnDisabled : null),
												disabled: busy,
												onClick: doAdd,
												children: busy ? "处理中…" : "添加"
											}),
											jsx.jsx("button", {
												type: "button",
												style: Object.assign({}, styles.btn, busy ? styles.btnDisabled : null),
												disabled: busy,
												onClick: doHealth,
												children: "健康检查（自动停用失效 key）"
											}),
											jsx.jsx("button", {
												type: "button",
												style: styles.btn,
												onClick: load,
												children: "刷新"
											})
										]
									}),
									jsx.jsx("p", { style: styles.hint, children: "重复 key 自动跳过；健康检查会真实调用每个 key 消耗少量积分。" })
								]
							})
						]
					}) : null
				]
			});
		}

		function apply(ctx) {
			ctx.slots.inject("settings.section", function () {
				return ctx.slots.register({
					name: "settings.section",
					id: "tavily-pool",
					order: 100,
					label: "Tavily 号池"
				}, TavilySection);
			});
		}

		exports.apply = apply;
		exports.inject = ["slots"];
		return module.exports;
	}
});
