# terminal_gallery.jl
# Julia Script

#=
Description: Prints out different astral objects from images. I thought this would just look cool.
Author: far_cds
Date: 3/9/2026
=#

using Images
using ImageTransformations
using ImageIO
using FileIO
using Base: basename
using Crayons

"""
    print_ascii_art(text_file::Union{IO, String}, kw::String)

Helper function that prints out pre-formatted lines from .txt files. Looks for keywords to
determine which lines it will print.
# Examples

print_ascii_art("$(julia_project_root)/path/to/file.txt", "")
"""
# TODO: Handle edge cases for no keywords or delimiters or both
function print_ascii_art(text_file_path::Union{IO, String}, kw::String; delimiter::String[]=["start", "end"])
    # Do not know if will use yet
    # foreach(println, eachline(text_file_path))

    if isfile(text_file_path)
        for line in eachline(text_file_path)
            # Look for any variation in the line that
            # matches the string
            if occursin(Regex("$(kw) $(delimiter[2])", "i"), line)
                break
            elseif !occursin("$(kw) $(delimiter[1])", line)
                 println(line)
            end
        end
    else
        @warn "Cannot find image file in" text_file_path
    end
end

function group_by_keywords(paths::Vector{String}, keywords::Vector{String})::Dict(String, Vector{String})
   kw_groups = Dict(
       kw => String[]
       for kw in keywords
   )

   for path in paths
       matches = [kw for kw in keywords if occursin(Regex(kw, "i"), path)]
       # Ignore paths with more than one defining keyword
       # e.g. file_kw1_kw2
       length(matches) == 1 && push!(kw_groups[only(matches)], path)
   end
   return kw_groups
end

"""
    display_image_to_terminal(image_paths::Vector{String}, keywords::Vector{String}; max_term_width=100, max_term_height)

Takes
"""
# TODO: Handle edge cases for multiple text files and if keyword images files are diff than keyword text files
function display_image_to_terminal(
    image_paths::Vector{String},
    text_file_path::Union{IO | String},
    keywords::Vector{String};
    max_term_width::Integer=100,
    max_term_height::Integer=50
)
    # To make image look square in terminal,
    # we need to use two pixels for width when converting from chars
    max_pix_height = max_term_height
    max_pix_width = div(max_term_width, 2)

    file_name = basename(@__FILE__)

    println("Running $(file_name)")
    println("Terminal Box Dimensions: $(max_term_height) x $(max_term_width)")
    println("Displayed in Terminal as: $(max_pix_height) columns x $(max_pix_width) rows\n")

    # Group paths by keyword to print in argument-defined order
    grouped_paths = group_by_keywords(image_paths, keywords)

    #Aesthetic
    println("YES, I CAN SEE IT...")

    for (i, (key, path)) in enumerate(grouped_paths)
        # TODO: Make this part optional and handle for multiple text files
        # Print out text in separate file
        print_ascii_art(text_file_path, keywords)

        # If images are transparent or grayscale
        img = RGB.(load(path))

        try
            h_org, w_org = size(img)

            scale_factor_height = max_pix_height / h_org
            scale_factor_width = max_pix_width / w_org
            scale_factor = min(scale_factor_height, scale_factor_width)

            # Resize image in pixels using smaller scale_factor to prevent stretch
            h_new = max(1, round(Int, h_org * scale_factor))
            w_new = max(1, round(Int, w_org * scale_factor))

            resized_img = imresize(img, (h_new, w_new))

            # Before image starts in case
            println()

            # Traverse image like a grid
            for row in 1:h_new
                for col in 1:w_new
                    pixel = resized_img[row, col]

                    r_val = round(Int, red(pixel) * 255)
                    g_val = round(Int, green(pixel) * 255)
                    b_val = round(Int, blue(pixel) * 255)

                    print(Crayon(background = (r_val, g_val, b_val)), "  ")
                end
                # Do not want to print used background color again
                println(Crayon(reset = true))
            end
            println(Crayon(reset = true))
        catch e
            if e isa MethodError
                @warn "Could not process image in $(path)..." e
            else
                # Not my error, do not want it
                rethrow(e)
            end
        end
    end
end


