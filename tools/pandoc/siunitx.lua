-- tools/pandoc/siunitx.lua
-- Convert \SI{<num>}{<unit>} => "<num> <unit>"
-- and   \SIrange{a}{b}{unit} => "a–b <unit>"

local function strip_braces(s)
  return s:gsub("^%{", ""):gsub("%}$", "")
end

function RawInline(el)
  if el.format ~= "tex" then return nil end
  local s = el.text

  -- \SIrange{a}{b}{unit}
  local ra, rb, ru = s:match("\\SIrange%s*%{([^}]*)%}%s*%{([^}]*)%}%s*%{([^}]*)%}")
  if ra and rb and ru then
    return pandoc.Str(ra .. "–" .. rb .. " " .. ru)
  end

  -- \SI{num}{unit}
  local num, unit = s:match("\\SI%s*%{([^}]*)%}%s*%{([^}]*)%}")
  if num and unit then
    return pandoc.Str(num .. " " .. unit)
  end

  return nil
end
