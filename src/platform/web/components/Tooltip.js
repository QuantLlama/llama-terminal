const Tooltip = ({ text, children, position = 'right' }) => {
  const posClasses = {
    right: "left-full ml-2 top-1/2 -translate-y-1/2",
    left: "right-full mr-2 top-1/2 -translate-y-1/2",
    top: "bottom-full mb-2 left-1/2 -translate-x-1/2",
    bottom: "top-full mt-2 left-1/2 -translate-x-1/2"
  };
  const arrowClasses = {
    right: "left-0 top-1/2 -ml-1 -mt-1 border-r-gray-800 border-t-transparent border-b-transparent border-l-transparent",
    left: "right-0 top-1/2 -mr-1 -mt-1 border-l-gray-800 border-t-transparent border-b-transparent border-r-transparent",
    top: "bottom-0 left-1/2 -mb-1 -ml-1 border-t-gray-800 border-r-transparent border-l-transparent border-b-transparent",
    bottom: "top-0 left-1/2 -mt-1 -ml-1 border-b-gray-800 border-r-transparent border-l-transparent border-t-transparent"
  };
  return (
    React.createElement("div", { className: "group relative flex items-center justify-center" },
    children,
    React.createElement("div", { className: `absolute ${posClasses[position]} px-2 py-1 bg-gray-800 text-white text-[10px] rounded border border-gray-700 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 shadow-xl` },
    text,
    React.createElement("div", { className: `absolute border-4 ${arrowClasses[position]}` })
    )
    ));
};