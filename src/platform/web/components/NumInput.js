const NumInput = ({
  label,
  value,
  onChange,
  step = 1,
  prefix = "",
  precision = 2,
  onConfirm,
  options = []
}) => {
  const [localVal, setLocalVal] = React.useState(String(value));
  React.useEffect(() => {
    const numericLocal = parseFloat(localVal);
    if (numericLocal !== value) {
      setLocalVal(String(value));
    }
  }, [value]);
  const handleValueChange = (newVal) => {
    let text = newVal.replace(",", ".");
    text = text.replace(/[^0-9.-]/g, "");
    const dots = (text.match(/\./g) || []).length;
    if (dots > 1) return;
    setLocalVal(text);
    if (
    text !== "" &&
    text !== "-" &&
    text !== "." &&
    !text.endsWith("."))
    {
      const parsed = parseFloat(text);
      if (!isNaN(parsed)) {
        onChange(parseFloat(parsed.toFixed(precision)));
      }
    }
  };
  return (
    React.createElement("div", {
      className: `bg-black border border-border rounded flex flex-col ${label ? "px-2 py-0.5" : "px-1.5 py-0.5"} focus-within:border-accent transition-colors relative group min-h-[22px]` },
    label &&
    React.createElement("label", { className: "text-[7px] text-muted uppercase font-black leading-tight" },
    label
    ),
    React.createElement("div", { className: "flex items-center" },
    React.createElement("span", { className: "text-xs text-muted mr-1" },
    prefix
    ),
    React.createElement("input", {
      type: "text",
      value: localVal,
      onChange: (e) =>
      handleValueChange(e.target.value),
      onBlur: () => {
        const parsed = parseFloat(localVal);
        if (
        isNaN(parsed) ||
        localVal === "" ||
        localVal === "-" ||
        localVal === ".")
        {
          onChange(0);
          setLocalVal("0");
        } else {
          const cleaned = parseFloat(
            parsed.toFixed(precision)
          );
          onChange(cleaned);
          setLocalVal(String(cleaned));
        }
      },
      onFocus: (e) => e.target.select(),
      className: "bg-black border-none text-white text-[11px] font-mono w-full outline-none text-center pr-6 py-0 appearance-none" }
    ),
    onConfirm &&
    React.createElement("button", {
      onClick: onConfirm,
      className: "absolute right-6 top-1/2 -translate-y-1/2 text-accent/40 hover:text-accent transition-colors z-10",
      title: "Confirm" },
    React.createElement("i", { className: "fas fa-check text-[7px]" })
    ),
    options.length > 0 &&
    React.createElement("div", { className: "absolute right-0 top-0 w-5 h-full flex items-center justify-center" },
    React.createElement("i", { className: "fas fa-chevron-down text-[6px] opacity-40 group-hover:opacity-100 transition-opacity" }),
    React.createElement("select", {
      className: "absolute inset-0 w-full h-full opacity-0 cursor-pointer z-20",
      onChange: (e) => {
        const val = parseFloat(
          e.target.value
        );
        if (!isNaN(val)) {
          onChange(val);
          setLocalVal(String(val));
        }
      },
      value: "" },
    React.createElement("option", { value: "", disabled: true }),
    options.map((opt) =>
    React.createElement("option", {
      key: opt,
      value: opt,
      className: "bg-[#1a1a1a]" },
    opt,
    prefix || (
    label &&
    label.
    toLowerCase().
    includes("leverage") ?
    "x" :
    "")
    )
    )
    )
    )
    )
    ));
};
window.NumInput = NumInput;