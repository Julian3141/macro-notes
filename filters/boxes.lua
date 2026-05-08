-- boxes.lua: converts Pandoc Div elements with class "box" into
-- HTML <details>/<summary> collapsible boxes.
-- The preprocessor emits:  ::: {.box .blue data-title="Title"} ... :::
-- This filter turns those into the <details class="box blue"> markup.

function Div(el)
  if not el.classes:includes('box') then return nil end

  local color = 'blue'
  for _, c in ipairs({'blue', 'red', 'green'}) do
    if el.classes:includes(c) then color = c; break end
  end

  local title = el.attributes['data-title'] or 'Box'

  local open_html  = '<details class="box ' .. color .. '">\n' ..
                     '<summary>' .. title .. '</summary>\n' ..
                     '<div class="box-content">'
  local close_html = '</div>\n</details>'

  local result = pandoc.List({ pandoc.RawBlock('html', open_html) })
  for _, block in ipairs(el.content) do
    result:insert(block)
  end
  result:insert(pandoc.RawBlock('html', close_html))
  return result
end
